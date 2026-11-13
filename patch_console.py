#!/usr/bin/env python3
"""Patch the copy of ElDewrito 0.7.1 that is already on a PS5, in place.

    python patch_console.py 192.168.1.50
    python patch_console.py 192.168.1.50 --dry-run
    python patch_console.py 192.168.1.50 --undo

It fetches the handful of files patch_for_ps5.py changes, runs the same steps
on them here, and sends back the ones that came out different. The game's
other files never leave the console.

The console is reached through the DevLoop payload (ps5loop, port 9112), which
must be loaded; close the game first. The address can also come from PS5_HOST.
The game is looked for under /data/playden-games; --game names its folder if
there is more than one.

The payload cannot make folders, so the originals of the files it replaces are
kept on this PC, in console_backup/ next to this script. --undo sends them
back. --no-glyphs is passed on to the patcher.
"""
import argparse
import os
import shutil
import socket
import sys
import tempfile

import patch_for_ps5 as patcher

PORT = int(os.environ.get('PS5LOOP_PORT', '9112'))
GAMES = '/data/playden-games'
BACKUP = os.path.join(patcher.HERE, 'console_backup')
SETTINGS = 'ui/screens/settings/'
FILES = ['mtndew.dll', 'binkw32.dll', 'binkw32_orig.dll', 'data/dewrito_prefs.cfg',
         'maps/fonts/font_package.bin', SETTINGS + 'settings.js', SETTINGS + 'settings.css',
         'ui/assets/settings/controller.png']
BUTTONS = 'ui/assets/buttons'


class Console:
    def __init__(self, host):
        self.host = host

    def ask(self, line, body=b'', timeout=300):
        """Send one command (and an upload's bytes). Returns the answer line
        and whatever bytes follow it."""
        try:
            connection = socket.create_connection((self.host, PORT), timeout=10)
        except OSError as error:
            raise SystemExit('the console did not answer on port %d (%s): is the DevLoop '
                             'payload loaded?' % (PORT, error.strerror or error))
        with connection:
            connection.settimeout(timeout)
            connection.sendall(line.encode() + b'\n' + body)
            data = b''
            while b'\n' not in data:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                data += chunk
            answer, _, rest = data.partition(b'\n')
            answer = answer.decode('utf-8', 'replace')
            if answer.startswith('ok file'):
                size = int(dict(w.split('=', 1) for w in answer.split() if '=' in w)['size'])
                while len(rest) < size:
                    chunk = connection.recv(1 << 20)
                    if not chunk:
                        raise SystemExit('%s: ended at %d of %d bytes' % (line, len(rest), size))
                    rest += chunk
                rest = rest[:size]
            return answer, rest

    def ls(self, path):
        """[(is a folder, name)], or None if there is no such folder."""
        answer, text = self.ask('ls ' + path)
        if not answer.startswith('ok'):
            return None
        rows = (line.split(None, 2) for line in text.decode('utf-8', 'replace').splitlines())
        return [(row[0] == 'd', row[2]) for row in rows if len(row) == 3]

    def get(self, path):
        answer, data = self.ask('get ' + path)
        return data if answer.startswith('ok file') else None

    def put(self, path, data):
        answer, _ = self.ask('put %s %d' % (path, len(data)), data)
        if not answer.startswith('ok'):
            raise SystemExit('could not write %s: %s' % (path, answer))

    def rm(self, path):
        self.ask('rm ' + path)


def find_game(console, wanted):
    if wanted:
        return wanted if wanted.startswith('/') else GAMES + '/' + wanted
    found = []
    for is_dir, name in console.ls(GAMES) or []:
        if is_dir and any(n == 'eldorado.exe' for _, n in console.ls(GAMES + '/' + name) or []):
            found.append(GAMES + '/' + name)
    if len(found) != 1:
        raise SystemExit('found %d folders with eldorado.exe under %s; name one with --game'
                         % (len(found), GAMES))
    return found[0]


def read_tree(root):
    out = {}
    for folder, _, names in os.walk(root):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, 'rb') as f:
                out[os.path.relpath(path, root).replace(os.sep, '/')] = f.read()
    return out


def write_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def patch(console, game, backup, args):
    wanted = FILES + [BUTTONS + '/' + name for is_dir, name in console.ls(game + '/' + BUTTONS) or []
                      if not is_dir and name.lower().endswith('.png')]
    with tempfile.TemporaryDirectory() as mirror:
        for rel in wanted:
            data = console.get(game + '/' + rel)
            if data is not None:
                write_file(os.path.join(mirror, rel), data)
        before = read_tree(mirror)
        for name in ('mtndew.dll', 'binkw32.dll'):
            if name not in before:
                raise SystemExit('%s is not in %s: is this the game folder?' % (name, game))
        # patching mtndew.dll for the first time reads the start of eldorado.exe
        if patcher.sha256(os.path.join(mirror, 'mtndew.dll')) == patcher.MTNDEW_ORIGINAL:
            write_file(os.path.join(mirror, 'eldorado.exe'), console.get(game + '/eldorado.exe') or b'')

        steps = [patcher.patch_mtndew, patcher.install_bridge, patcher.set_prefs]
        if not args.no_glyphs:
            steps += [patcher.patch_glyphs, patcher.patch_font_package,
                      patcher.patch_button_names, patcher.patch_controller_pic]
        for step in steps:
            print('  ' + step(mirror))
        after = read_tree(mirror)

    # what the patcher keeps as originals stays on this PC, except the real
    # Bink DLL, which the bridge needs beside it
    send = [rel for rel in sorted(after) if after[rel] != before.get(rel)
            and (rel in before or rel == 'binkw32_orig.dll')]
    if not send:
        print('Nothing to send: the console copy is already patched.')
        return
    for rel in send:
        print('  %s %s (%d bytes)' % ('would send' if args.dry_run else 'sending', rel, len(after[rel])))
        if args.dry_run:
            continue
        if rel in before and not os.path.exists(os.path.join(backup, rel)):
            write_file(os.path.join(backup, rel), before[rel])
        console.put(game + '/' + rel, after[rel])
    if not args.dry_run:
        print('Sent %d files. The originals of the ones replaced are in %s' % (len(send), backup))
        print('In Playden, the program arguments must be: --single-process --in-process-gpu')


def undo(console, game, backup, args):
    kept = read_tree(backup) if os.path.isdir(backup) else {}
    if not kept:
        raise SystemExit('nothing to undo: no originals for this game in %s' % backup)
    for rel in sorted(kept):
        print('  %s %s' % ('would restore' if args.dry_run else 'restoring', rel))
        if not args.dry_run:
            console.put(game + '/' + rel, kept[rel])
    if 'binkw32.dll' in kept:                            # the bridge is gone: so is its partner
        print('  %s binkw32_orig.dll' % ('would remove' if args.dry_run else 'removing'))
        if not args.dry_run:
            console.rm(game + '/binkw32_orig.dll')
    if not args.dry_run:
        shutil.rmtree(backup)
        print('Restored %d files.' % len(kept))


def main():
    ap = argparse.ArgumentParser(description='Patch the ElDewrito 0.7.1 copy on a PS5 in place.')
    ap.add_argument('host', nargs='?', default=os.environ.get('PS5_HOST'),
                    help="the console's address (default: PS5_HOST)")
    ap.add_argument('--game', help='the game folder on the console, if it cannot be found')
    ap.add_argument('--dry-run', action='store_true', help='show what would be sent; send nothing')
    ap.add_argument('--undo', action='store_true', help='send the kept originals back')
    ap.add_argument('--no-glyphs', action='store_true',
                    help='keep the Xbox button icons, names and controller picture')
    args = ap.parse_args()
    if not args.host:
        ap.error("give the console's address, or set PS5_HOST")

    console = Console(args.host)
    game = find_game(console, args.game)
    backup = os.path.join(BACKUP, os.path.basename(game))
    print(game)
    (undo if args.undo else patch)(console, game, backup, args)


if __name__ == '__main__':
    main()
