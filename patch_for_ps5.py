#!/usr/bin/env python3
"""Patch an ElDewrito 0.7.1 folder so it runs on a PS5 under Playden.

    python patch_for_ps5.py "C:\\path\\to\\ElDewrito_0.7.1"
    python patch_for_ps5.py "C:\\path\\to\\ElDewrito_0.7.1" --undo
    python patch_for_ps5.py "C:\\path\\to\\ElDewrito_0.7.1" --no-glyphs

What it does, each step only if not already done:

1. mtndew.dll: six lookups of the game's base address use 0x400000 instead of
   a module snapshot, which fails under Playden's Wine (start-up crash).
   The original is kept as mtndew.dll.orig.
2. binkw32.dll: replaced by the bridge (dewbridge.dll, next to this script),
   which gives the web screens their window.dewQuery in single-process mode.
   The original is kept as binkw32_orig.dll, which the bridge forwards to.
3. data/dewrito_prefs.cfg: Game.CEFGpuEnable "0" (software drawing of the web
   screens) and Settings.Gamepad "1".
4. ui/assets/buttons: the Xbox button icons of the web screens are replaced
   with PS5 (DualSense) ones. The originals are kept in
   ui/assets/buttons_xbox_orig. In Settings > Controls the buttons are listed
   by their PS5 names and the Xbox controller photo becomes a DualSense
   drawing (originals kept as settings.js.xbox_orig, controller.png.xbox_orig).
   Skip all of this with --no-glyphs.

It does not set the launch arguments. In Playden, give the game:
    --single-process --in-process-gpu
"""
import argparse
import hashlib
import math
from array import array
import os
import re
import shutil
import struct
import sys
import zlib

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


# --- PS5 button glyphs -------------------------------------------------------
#
# The web screens show controller prompts as PNGs in ui/assets/buttons, named
# 360_<button>.png (0.6 also had an XboxOne_ set, and kept them under
# mods/ui/web). They are replaced with DualSense glyphs drawn here, each at the
# pixel size of the file it replaces, so no image files are needed.
# A PNG named <button>.png (A.png, LB.png, ...) in a ps5_glyphs folder next to
# this script is used instead of the drawn one.

# where the icons are: 0.7.1 first, then the layout of 0.6
BUTTONS_DIRS = [os.path.join('ui', 'assets', 'buttons'),
                os.path.join('mods', 'ui', 'web', 'assets', 'buttons')]
BACKUP_SUFFIX = '_xbox_orig'            # ui/assets/buttons_xbox_orig
GLYPH_OVERRIDES = os.path.join(HERE, 'ps5_glyphs')
ICON_SETS = ('360', 'XboxOne')
WHITE = (255, 255, 255)


def _seg(p, a, b):
    """Distance from point p to the segment a-b."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = p[0] - a[0], p[1] - a[1]
    ll = vx * vx + vy * vy
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / ll)) if ll else 0.0
    return math.hypot(wx - t * vx, wy - t * vy)


def _line(points, width, closed=False):
    pts = list(points)
    pairs = list(zip(pts, pts[1:] + pts[:1])) if closed else list(zip(pts, pts[1:]))
    return lambda p: min(_seg(p, a, b) for a, b in pairs) - width / 2.0


def _disc(c, r):
    return lambda p: math.hypot(p[0] - c[0], p[1] - c[1]) - r


def _box(c, half, r):
    def f(p):
        qx, qy = abs(p[0] - c[0]) - half[0] + r, abs(p[1] - c[1]) - half[1] + r
        return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r
    return f


def _outline(f, width):
    return lambda p: abs(f(p)) - width / 2.0


def _arc(c, r, a0, a1, steps=14):
    """Points along an arc, angles in degrees, y pointing down."""
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / steps)))
            for i in range(steps + 1)]


# stroke letters in a box 1 high: (width, [polylines])
_LETTERS = {
    'L': (0.55, [[(0, 0), (0, 1), (0.55, 1)]]),
    'R': (0.58, [[(0, 1), (0, 0)] + _arc((0.3, 0.25), 0.25, -90, 90) + [(0, 0.5)],
                 [(0.25, 0.5), (0.58, 1)]]),
    '1': (0.35, [[(0, 0.22), (0.35, 0), (0.35, 1)]]),
    '2': (0.58, [_arc((0.28, 0.28), 0.28, 180, 400) + [(0, 1), (0.58, 1)]]),
    '3': (0.54, [_arc((0.27, 0.25), 0.25, 200, 450) + _arc((0.27, 0.74), 0.26, 270, 520)]),
}


def _text(s, c, height, width):
    total = sum(_LETTERS[ch][0] for ch in s) + 0.28 * (len(s) - 1)
    x = c[0] - total * height / 2.0
    y = c[1] - height / 2.0
    parts = []
    for ch in s:
        w, lines = _LETTERS[ch]
        for pts in lines:
            parts.append(_line([(x + px * height, y + py * height) for px, py in pts], width))
        x += (w + 0.28) * height
    return lambda p: min(f(p) for f in parts)


def _face(symbol, colour):
    return [(_disc((50, 50), 42), (38, 40, 48)),
            (_outline(_disc((50, 50), 42), 4), (214, 218, 226)),
            (symbol, colour)]


def _bumper(label):
    return [(_outline(_box((50, 50), (40, 24), 13), 5), WHITE),
            (_text(label, (50, 50), 24, 5.5), WHITE)]


def _trigger(label):
    return [(_outline(_box((50, 50), (30, 38), 17), 5), WHITE),
            (_text(label, (50, 52), 24, 5.5), WHITE)]


def _stick(label):
    layers = [(_outline(_disc((50, 50), 40), 5), WHITE)]
    if len(label) == 1:                       # plain stick: a second, inner ring
        layers.append((_outline(_disc((50, 50), 28), 4), WHITE))
    layers.append((_text(label, (50, 50), 26 if len(label) == 1 else 24, 5.5), WHITE))
    return layers


def _dpad(direction=None):
    def cross(p):
        return min(_box((50, 50), (40, 14), 5)(p), _box((50, 50), (14, 40), 5)(p))
    layers = [(_outline(cross, 5), WHITE)]
    if direction:
        dx, dy = direction
        # the arm on that side, filled
        layers.append((lambda p: max(cross(p), 14 - (p[0] - 50) * dx - (p[1] - 50) * dy), WHITE))
    return layers


def _options():
    return [(_line([(27, y), (73, y)], 8), WHITE) for y in (31, 50, 69)]


def _create():
    rays = [_line([(50 + 12 * math.cos(math.radians(a)), 44 + 12 * math.sin(math.radians(a))),
                   (50 + 29 * math.cos(math.radians(a)), 44 + 29 * math.sin(math.radians(a)))], 7)
            for a in (-140, -90, -40)]
    return [(lambda p: min(f(p) for f in rays), WHITE),
            (_box((50, 70), (8, 16), 8), WHITE)]


# Xbox name used in the file names -> DualSense glyph
GLYPHS = {
    'A': lambda: _face(lambda p: min(_line([(35, 35), (65, 65)], 7)(p),
                                     _line([(35, 65), (65, 35)], 7)(p)), (124, 178, 232)),
    'B': lambda: _face(_outline(_disc((50, 50), 18), 7), (255, 102, 102)),
    'X': lambda: _face(_outline(_box((50, 50), (17, 17), 2), 7), (234, 130, 220)),
    'Y': lambda: _face(_line([(50, 29), (70, 63), (30, 63)], 7, closed=True), (64, 226, 160)),
    'LB': lambda: _bumper('L1'),
    'RB': lambda: _bumper('R1'),
    'LT': lambda: _trigger('L2'),
    'RT': lambda: _trigger('R2'),
    'LS': lambda: _stick('L'),
    'RS': lambda: _stick('R'),
    'LS_Click': lambda: _stick('L3'),
    'RS_Click': lambda: _stick('R3'),
    'Start': _options,
    'Back': _create,
    'Dpad': _dpad,
    'Dpad_Up': lambda: _dpad((0, -1)),
    'Dpad_Down': lambda: _dpad((0, 1)),
    'Dpad_Left': lambda: _dpad((-1, 0)),
    'Dpad_Right': lambda: _dpad((1, 0)),
}


def _png(layers, width=100, height=100):
    """Draw the layers (distance function, colour), in order, as an RGBA PNG.
    The layers are laid out on a 100x100 square, scaled to fit and centred."""
    return _render(layers, width, height, 100, 100)


def _render(layers, width, height, design_w, design_h, comment=None):
    """Draw layers laid out on design_w x design_h, scaled to fit and centred.
    A layer may carry a third item, the box (x0, y0, x1, y1) in design units
    outside which it draws nothing; that only saves time."""
    scale = min(float(width) / design_w, float(height) / design_h)
    ox, oy = (width - design_w * scale) / 2.0, (height - design_h * scale) / 2.0
    zero = bytes(4 * width * height)
    red, green, blue, alpha = (array('f', zero) for _ in range(4))   # premultiplied
    for layer in layers:
        f, (cr, cg, cb) = layer[0], layer[1]
        x0, y0, x1, y1 = 0, 0, width, height
        if len(layer) > 2:
            box = layer[2]
            x0, y0 = max(0, int(box[0] * scale + ox) - 1), max(0, int(box[1] * scale + oy) - 1)
            x1 = min(width, int(box[2] * scale + ox) + 2)
            y1 = min(height, int(box[3] * scale + oy) + 2)
        for y in range(y0, y1):
            py = (y + 0.5 - oy) / scale
            i = y * width + x0
            for x in range(x0, x1):
                cov = 0.5 - f(((x + 0.5 - ox) / scale, py)) * scale
                if cov > 0:
                    if cov >= 1:
                        red[i], green[i], blue[i], alpha[i] = cr, cg, cb, 1.0
                    else:
                        keep = 1 - cov
                        red[i] = red[i] * keep + cr * cov
                        green[i] = green[i] * keep + cg * cov
                        blue[i] = blue[i] * keep + cb * cov
                        alpha[i] = alpha[i] * keep + cov
                i += 1

    rows = bytearray()
    for y in range(height):
        rows.append(0)                                   # filter: none
        for i in range(y * width, (y + 1) * width):
            a = alpha[i]
            if a > 0:
                rows += bytes((min(255, int(red[i] / a + 0.5)), min(255, int(green[i] / a + 0.5)),
                               min(255, int(blue[i] / a + 0.5)), min(255, int(a * 255 + 0.5))))
            else:
                rows += b'\0\0\0\0'

    def chunk(kind, body):
        return (struct.pack('>I', len(body)) + kind + body
                + struct.pack('>I', zlib.crc32(kind + body)))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + (chunk(b'tEXt', b'Comment\0' + comment) if comment else b'')
            + chunk(b'IDAT', zlib.compress(bytes(rows), 9))
            + chunk(b'IEND', b''))


def glyph_png(name, width=100, height=100):
    override = os.path.join(GLYPH_OVERRIDES, name + '.png')
    if os.path.isfile(override):
        with open(override, 'rb') as f:
            return f.read()
    return _png(GLYPHS[name](), width, height)


def png_size(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        return 100, 100
    width, height = struct.unpack_from('>II', data, 16)
    return (width, height) if 0 < width <= 2048 and 0 < height <= 2048 else (100, 100)


def buttons_dir(folder, suffix=''):
    for rel in BUTTONS_DIRS:
        if os.path.isdir(os.path.join(folder, rel + suffix)):
            return rel
    return None


def patch_glyphs(folder):
    rel = buttons_dir(folder)
    if not rel:
        return 'button glyphs: %s not found, skipped' % BUTTONS_DIRS[0]
    buttons = os.path.join(folder, rel)
    backup = buttons + BACKUP_SUFFIX

    pattern = re.compile(r'^(%s)_(.+)\.png$' % '|'.join(ICON_SETS))
    cache, changed, same, unknown = {}, 0, 0, []
    for fname in sorted(os.listdir(buttons)):
        m = pattern.match(fname)
        if not m:
            continue
        name = m.group(2)
        if name not in GLYPHS:
            unknown.append(fname)
            continue
        path = os.path.join(buttons, fname)
        kept = os.path.join(backup, fname)
        with open(path, 'rb') as f:
            current = f.read()
        # size of the Xbox icon: the kept original if this one was replaced before
        if os.path.exists(kept):
            with open(kept, 'rb') as f:
                size = png_size(f.read())
        else:
            size = png_size(current)
        if (name, size) not in cache:
            cache[name, size] = glyph_png(name, *size)
        new = cache[name, size]
        if current == new:
            same += 1
            continue
        os.makedirs(backup, exist_ok=True)
        if not os.path.exists(kept):
            shutil.copy2(path, kept)
        with open(path, 'wb') as f:
            f.write(new)
        changed += 1

    if not changed and not same:
        return 'button glyphs: no Xbox icon files in %s, skipped' % rel
    msg = ('button glyphs: already PS5' if not changed else
           'button glyphs: %d icons replaced with PS5 ones (originals kept in %s)'
           % (changed, rel + BACKUP_SUFFIX))
    if unknown:
        msg += '; no PS5 glyph for %s, left alone' % ', '.join(unknown)
    return msg


# --- PS5 names and picture in Settings > Controls -----------------------------
#
# The controller tab lists the buttons by their Xbox names in every binding
# drop-down, and shows a photo of an Xbox One pad with lines out to the labels.
# The names are changed where they are displayed only: the values the page
# sends to the game stay "A", "LB", ... The photo is replaced by a drawing of a
# DualSense whose lines leave the picture at the same places, so the page's
# labels still line up.

KEPT = '.xbox_orig'
SETTINGS_JS = os.path.join('ui', 'screens', 'settings', 'settings.js')
NAME_OLD = b'opt.textContent = buttons[x];'
NAME_NEW = (b"opt.textContent = ({A:'Cross',B:'Circle',X:'Square',Y:'Triangle',"
            b"RB:'R1',LB:'L1',LT:'L2',RT:'R2',Start:'Options',Back:'Create',"
            b"LS:'L3',RS:'R3'})[buttons[x]] || buttons[x];")

CONTROLLER_PIC = os.path.join('ui', 'assets', 'settings', 'controller.png')
CONTROLLER_SIZE = (1024, 670)
CONTROLLER_MARK = b'patch_for_ps5 DualSense 1'      # change when the drawing changes

# label lines: where each leaves the picture (first point, as in the Xbox
# photo) to the button it names (last point)
LEADERS = [
    [(268, 40), (268, 122)],                                            # LT -> L2
    [(765, 40), (765, 122)],                                            # RT -> R2
    [(125, 113), (178, 160)],                                           # LB -> L1
    [(908, 113), (850, 160)],                                           # RB -> R1
    [(83, 235), (648, 235), (662, 220)],                                # Start -> Options
    [(33, 285), (120, 285), (145, 260), (322, 260), (354, 224)],        # Back -> Create
    [(5, 345), (112, 345), (167, 290), (292, 290), (346, 400)],         # LS
    [(5, 437), (118, 437), (158, 397), (158, 340), (178, 322), (226, 324)],   # Up
    [(10, 513), (150, 513), (196, 364)],                                # Left
    [(20, 600), (205, 600), (232, 398)],                                # Down
    [(430, 630), (430, 585), (300, 455), (270, 364)],                   # Right
    [(965, 232), (752, 232), (725, 259), (725, 321)],                   # X -> Square
    [(985, 308), (842, 308), (822, 290), (805, 290)],                   # Y -> Triangle
    [(1005, 380), (872, 380), (854, 362)],                              # B -> Circle
    [(1020, 453), (832, 453), (798, 418)],                              # A -> Cross
    [(1010, 548), (735, 548), (672, 458)],                              # RS
]


def _boxed(f, colour, x0, y0, x1, y1):
    return (f, colour, (x0, y0, x1, y1))


def _around(c, r, f, colour):
    return _boxed(f, colour, c[0] - r, c[1] - r, c[0] + r, c[1] + r)


def _controller_layers():
    shell, edge, dark, mid = (232, 235, 240), (140, 146, 158), (38, 40, 48), (96, 100, 112)
    layers = []

    for side in (1, -1):                                 # left, then mirrored right
        def mx(x):
            return 512 - side * (512 - x)
        layers.append(_around((mx(240), 128), 70, _box((mx(240), 128), (60, 34), 24), dark))   # L2
        layers.append(_around((mx(232), 172), 95, _box((mx(232), 172), (88, 26), 20), mid))    # L1

    grips = [_line([(200, 420), (172, 565)], 156), _line([(824, 420), (852, 565)], 156)]
    middle = _box((512, 340), (395, 165), 120)

    def body(p):
        return min(middle(p), grips[0](p), grips[1](p))
    layers.append(_boxed(body, shell, 85, 165, 939, 652))
    layers.append(_boxed(_outline(body, 3), edge, 85, 165, 939, 652))

    layers.append(_boxed(_box((512, 262), (118, 78), 22), (58, 61, 72), 390, 180, 634, 344))   # touchpad
    for x in (360, 664):                                 # Create, Options
        layers.append(_around((x, 212), 20, _box((x, 212), (8, 17), 8), dark))
    layers.append(_around((512, 430), 17, _disc((512, 430), 15), dark))                        # PS

    def cross(p):
        return min(_box((232, 358), (48, 17), 5)(p), _box((232, 358), (17, 48), 5)(p))
    layers.append(_around((232, 358), 50, cross, dark))

    for c in ((380, 430), (644, 430)):                   # sticks
        layers.append(_around(c, 54, _disc(c, 52), dark))
        layers.append(_around(c, 40, _outline(_disc(c, 34), 4), mid))

    def face(c, symbol, colour):
        layers.append(_around(c, 28, _disc(c, 26), dark))
        layers.append(_around(c, 18, symbol, colour))
    x, y = 780, 290
    face((x, y), _line([(x, y - 12), (x + 12, y + 9), (x - 12, y + 9)], 4, closed=True), (64, 226, 160))
    x, y = 835, 345
    face((x, y), _outline(_disc((x, y), 11), 4), (255, 102, 102))
    x, y = 780, 400
    face((x, y), lambda p, x=x, y=y: min(_line([(x - 10, y - 10), (x + 10, y + 10)], 4)(p),
                                         _line([(x - 10, y + 10), (x + 10, y - 10)], 4)(p)),
         (124, 178, 232))
    x, y = 725, 345
    face((x, y), _outline(_box((x, y), (10, 10), 1), 4), (234, 130, 220))

    for pts in LEADERS:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        box = (min(xs) - 12, min(ys) - 12, max(xs) + 12, max(ys) + 12)
        end = pts[-1]
        for width, radius, colour in ((8, 9.5, (20, 22, 28)), (3.5, 6.5, WHITE)):
            layers.append((_line(pts, width), colour, box))
            layers.append(_around(end, radius + 1, _disc(end, radius), colour))
    return layers


def _keep_and_write(path, data):
    if not os.path.exists(path + KEPT):
        shutil.copy2(path, path + KEPT)
    with open(path, 'wb') as f:
        f.write(data)


def patch_button_names(folder):
    path = os.path.join(folder, SETTINGS_JS)
    if not os.path.isfile(path):
        return 'button names: %s not found, skipped' % SETTINGS_JS
    with open(path, 'rb') as f:
        data = f.read()
    if NAME_NEW in data:
        return 'button names: already PS5'
    if data.count(NAME_OLD) != 1:
        return 'button names: %s is not as expected, left alone' % SETTINGS_JS
    _keep_and_write(path, data.replace(NAME_OLD, NAME_NEW))
    return 'button names: PS5 names in the controller settings (original kept as settings.js%s)' % KEPT


def patch_controller_pic(folder):
    path = os.path.join(folder, CONTROLLER_PIC)
    if not os.path.isfile(path):
        return 'controller picture: %s not found, skipped' % CONTROLLER_PIC
    with open(path, 'rb') as f:
        data = f.read()
    override = os.path.join(GLYPH_OVERRIDES, 'controller.png')
    if os.path.isfile(override):
        with open(override, 'rb') as f:
            new = f.read()
        if data == new:
            return 'controller picture: already PS5'
    elif CONTROLLER_MARK in data[:200]:
        return 'controller picture: already PS5'
    elif not os.path.exists(path + KEPT) and png_size(data) != CONTROLLER_SIZE:
        return 'controller picture: %s is not as expected, left alone' % CONTROLLER_PIC
    else:
        new = _render(_controller_layers(), CONTROLLER_SIZE[0], CONTROLLER_SIZE[1],
                      CONTROLLER_SIZE[0], CONTROLLER_SIZE[1], CONTROLLER_MARK)
    _keep_and_write(path, new)
    return 'controller picture: DualSense drawing (original kept as controller.png%s)' % KEPT


def undo_kept(folder, rel, what):
    path = os.path.join(folder, rel)
    if not os.path.exists(path + KEPT):
        return '%s: no %s%s, left alone' % (what, os.path.basename(rel), KEPT)
    os.replace(path + KEPT, path)
    return '%s: original restored' % what


def undo_glyphs(folder):
    rel = buttons_dir(folder, BACKUP_SUFFIX)
    if not rel:
        return 'button glyphs: no %s, left alone' % (BUTTONS_DIRS[0] + BACKUP_SUFFIX)
    buttons = os.path.join(folder, rel)
    backup = buttons + BACKUP_SUFFIX
    count = 0
    for fname in os.listdir(backup):
        os.replace(os.path.join(backup, fname), os.path.join(buttons, fname))
        count += 1
    os.rmdir(backup)
    return 'button glyphs: %d original icons restored' % count


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
    out.append(undo_glyphs(folder))
    out.append(undo_kept(folder, SETTINGS_JS, 'button names'))
    out.append(undo_kept(folder, CONTROLLER_PIC, 'controller picture'))
    out.append('dewrito_prefs.cfg: left as it is (change Game.CEFGpuEnable back by hand if wanted)')
    return out


def main():
    ap = argparse.ArgumentParser(description='Patch an ElDewrito 0.7.1 folder for PS5 (Playden).')
    ap.add_argument('folder', help='the game folder, the one that holds eldorado.exe')
    ap.add_argument('--undo', action='store_true',
                    help='put the original DLLs and Xbox icons, names and picture back')
    ap.add_argument('--no-glyphs', action='store_true',
                    help='keep the Xbox button icons, names and controller picture')
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
        if not args.no_glyphs:
            lines += [patch_glyphs(folder), patch_button_names(folder),
                      patch_controller_pic(folder)]
    for line in lines:
        print('  ' + line)
    if not args.undo:
        print('In Playden, set the program arguments to: --single-process --in-process-gpu')


if __name__ == '__main__':
    main()
