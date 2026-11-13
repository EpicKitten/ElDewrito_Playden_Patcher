#!/usr/bin/env python3
"""Patch an ElDewrito 0.7.1 folder so it runs on a PS5 under Playden.

    python patch_for_ps5.py "C:\\path\\to\\ElDewrito_0.7.1"
    python patch_for_ps5.py "C:\\path\\to\\ElDewrito_0.7.1" --undo

What it does, each step only if not already done:

1. mtndew.dll: six lookups of the game's base address use 0x400000 instead of
   a module snapshot, which fails under Playden's Wine (start-up crash).
   The original is kept as mtndew.dll.orig.
2. binkw32.dll: replaced by the bridge (dewbridge.dll, next to this script),
   which gives the web screens their window.dewQuery in single-process mode.
   The original is kept as binkw32_orig.dll, which the bridge forwards to.
3. data/dewrito_prefs.cfg: Game.CEFGpuEnable "0" (software drawing of the web
   screens) and Settings.Gamepad "1".

It does not set the launch arguments. In Playden, give the game:
    --single-process --in-process-gpu
"""
import argparse
import hashlib
import os
import re
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(HERE, 'dewbridge.dll')

MTNDEW_ORIGINAL = 'b05f0704bf0567b8ae01b343ba5f9d3089de836a4e02f33d69f6cab4356c162f'
MTNDEW_PATCHED = '0142161045704600aded49cb91d80e5dbc33db78ab07843674a631d5de46aa88'

# (address of "cmp edi,-1", address of "mov [cache],eax") in mtndew.dll 0.7.1
SITES = [
    (0x100eeb5a, 0x100eeb8f),
    (0x10153805, 0x10153840),
    (0x101538a2, 0x101538d9),
    (0x10153935, 0x1015396c),
    (0x101539ce, 0x10153a05),
    (0x101854de, 0x10185522),
]
PREFS = [('Game.CEFGpuEnable', '0'), ('Settings.Gamepad', '1')]


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def is_bridge(path):
    with open(path, 'rb') as f:
        return b'dewbridge: ' in f.read()


def patch_mtndew(folder):
    dll = os.path.join(folder, 'mtndew.dll')
    bak = dll + '.orig'
    digest = sha256(dll)
    if digest == MTNDEW_PATCHED:
        return 'mtndew.dll: already patched'
    if digest != MTNDEW_ORIGINAL:
        raise SystemExit('mtndew.dll is not the 0.7.1 file this patch was made for '
                         '(sha256 %s); nothing changed in it' % digest)

    with open(os.path.join(folder, 'eldorado.exe'), 'rb') as f:
        head = f.read(0x400)
    pe = struct.unpack_from('<I', head, 0x3c)[0]
    if struct.unpack_from('<I', head, pe + 24 + 28)[0] != 0x400000:
        raise SystemExit('eldorado.exe does not load at 0x400000; not patching')

    with open(dll, 'rb') as f:
        data = bytearray(f.read())
    for cmp_va, store_va in SITES:
        o = cmp_va - 0x10001000 + 0x400          # .text: va 0x1000, file 0x400
        s = store_va - 0x10001000 + 0x400
        if data[o:o + 4] != bytes.fromhex('83ffff75') or data[o + 5:o + 7] != b'\x33\xc0':
            raise SystemExit('mtndew.dll: unexpected bytes at %x' % cmp_va)
        if data[s:s + 5] != bytes.fromhex('a354683212'):
            raise SystemExit('mtndew.dll: unexpected bytes at %x' % store_va)
        # mov eax, 0x400000 ; jmp short <store>
        data[o:o + 7] = b'\xb8' + struct.pack('<I', 0x400000) + b'\xeb' + bytes([store_va - (cmp_va + 7)])
    if hashlib.sha256(data).hexdigest() != MTNDEW_PATCHED:
        raise SystemExit('mtndew.dll: patched result is not the expected file; nothing written')

    if not os.path.exists(bak):
        shutil.copy2(dll, bak)
    with open(dll, 'wb') as f:
        f.write(data)
    return 'mtndew.dll: patched (original kept as mtndew.dll.orig)'


def install_bridge(folder):
    dll = os.path.join(folder, 'binkw32.dll')
    orig = os.path.join(folder, 'binkw32_orig.dll')
    if not os.path.exists(BRIDGE):
        raise SystemExit('dewbridge.dll is not next to this script (%s)' % HERE)
    if is_bridge(dll):
        if not os.path.exists(orig):
            raise SystemExit('binkw32.dll is the bridge but binkw32_orig.dll is missing')
        if sha256(dll) == sha256(BRIDGE):
            return 'binkw32.dll: bridge already installed'
        shutil.copyfile(BRIDGE, dll)
        return 'binkw32.dll: bridge updated to the copy next to this script'
    if os.path.exists(orig):
        raise SystemExit('binkw32_orig.dll already exists but binkw32.dll is not the bridge; '
                         'sort that out by hand')
    os.rename(dll, orig)
    shutil.copyfile(BRIDGE, dll)
    return 'binkw32.dll: bridge installed (original kept as binkw32_orig.dll)'


def set_prefs(folder):
    path = os.path.join(folder, 'data', 'dewrito_prefs.cfg')
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(b''.join(('%s "%s"\r\n' % p).encode() for p in PREFS))
        return 'dewrito_prefs.cfg: created with %s' % ', '.join('%s "%s"' % p for p in PREFS)

    with open(path, 'rb') as f:
        text = f.read()
    new = text
    eol = b'\r\n' if b'\r\n' in text else b'\n'
    for name, value in PREFS:
        line = ('%s "%s"' % (name, value)).encode()
        pattern = re.compile(rb'^' + re.escape(name.encode()) + rb'[ \t]+"[^"\r\n]*"', re.M)
        if pattern.search(new):
            new = pattern.sub(line, new, count=1)
        else:
            if new and not new.endswith(b'\n'):
                new += eol
            new += line + eol
    if new == text:
        return 'dewrito_prefs.cfg: already set'
    with open(path, 'wb') as f:
        f.write(new)
    return 'dewrito_prefs.cfg: set %s' % ', '.join('%s "%s"' % p for p in PREFS)


def undo(folder):
    out = []
    dll, bak = os.path.join(folder, 'mtndew.dll'), os.path.join(folder, 'mtndew.dll.orig')
    if os.path.exists(bak):
        os.replace(bak, dll)
        out.append('mtndew.dll: original restored')
    else:
        out.append('mtndew.dll: no mtndew.dll.orig, left alone')
    bink, orig = os.path.join(folder, 'binkw32.dll'), os.path.join(folder, 'binkw32_orig.dll')
    if os.path.exists(orig) and is_bridge(bink):
        os.replace(orig, bink)
        out.append('binkw32.dll: original restored')
    else:
        out.append('binkw32.dll: bridge not installed, left alone')
    out.append('dewrito_prefs.cfg: left as it is (change Game.CEFGpuEnable back by hand if wanted)')
    return out


def main():
    ap = argparse.ArgumentParser(description='Patch an ElDewrito 0.7.1 folder for PS5 (Playden).')
    ap.add_argument('folder', help='the game folder, the one that holds eldorado.exe')
    ap.add_argument('--undo', action='store_true', help='put the original DLLs back')
    args = ap.parse_args()

    folder = os.path.abspath(args.folder)
    for name in ('eldorado.exe', 'mtndew.dll', 'binkw32.dll'):
        if not os.path.isfile(os.path.join(folder, name)):
            raise SystemExit('%s not found in %s: is this the game folder?' % (name, folder))

    print(folder)
    if args.undo:
        lines = undo(folder)
    else:
        # mtndew first: it refuses an unknown file before anything else is touched
        lines = [patch_mtndew(folder), install_bridge(folder), set_prefs(folder)]
    for line in lines:
        print('  ' + line)
    if not args.undo:
        print('In Playden, set the program arguments to: --single-process --in-process-gpu')


if __name__ == '__main__':
    main()
