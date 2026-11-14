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
   photo, with the labels around it moved to match (originals kept as
   settings.js.xbox_orig, controller.png.xbox_orig, settings.css.xbox_orig).
   The original game's own menus get PS5 glyphs too: the Xbox button
   characters in maps/fonts/font_package.bin are redrawn (original kept as
   font_package.bin.xbox_orig). A mod's .pak brings its own fonts and cannot
   be changed on disk, so dewbridge_ps5_glyphs.txt is also put in the game
   folder: while it is there, the bridge redraws the button characters of
   every font the game loads. Skip all of this with --no-glyphs.

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
KEPT = '.xbox_orig'                      # put after a file's name for its original


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


def _raster(layers, width, height, design_w=100.0, design_h=100.0):
    """Draw the layers (distance function, colour), in order. The layers are
    laid out on design_w x design_h, scaled to fit width x height and centred.
    Returns one (r, g, b, a) per pixel, 0..255, row by row."""
    scale = min(width / design_w, height / design_h)
    ox, oy = (width - design_w * scale) / 2.0, (height - design_h * scale) / 2.0
    zero = bytes(4 * width * height)
    red, green, blue, alpha = (array('f', zero) for _ in range(4))   # premultiplied
    for f, (cr, cg, cb) in layers:
        for y in range(height):
            py = (y + 0.5 - oy) / scale
            i = y * width
            for x in range(width):
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
    out = []
    for i in range(width * height):
        a = alpha[i]
        if a > 0:
            out.append((min(255, int(red[i] / a + 0.5)), min(255, int(green[i] / a + 0.5)),
                        min(255, int(blue[i] / a + 0.5)), min(255, int(a * 255 + 0.5))))
        else:
            out.append((0, 0, 0, 0))
    return out


def _png(layers, width=100, height=100):
    """The layers, laid out on a 100x100 square, as an RGBA PNG."""
    pixels = _raster(layers, width, height)
    rows = bytearray()
    for y in range(height):
        rows.append(0)                                   # filter: none
        for pixel in pixels[y * width:(y + 1) * width]:
            rows += bytes(pixel)

    def chunk(kind, body):
        return (struct.pack('>I', len(body)) + kind + body
                + struct.pack('>I', zlib.crc32(kind + body)))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
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


# --- PS5 button glyphs in the original game's menus ---------------------------
#
# The game's own menus and HUD (not web pages) print button prompts as
# characters U+E100.. of maps/fonts/font_package.bin, in the fonts conduit-16
# and conduit-18. The file is a 0x8000-byte header block followed by
# 0x8000-byte packages; a package starts with (header size, character count,
# ...) as 16-bit values and a table of (font << 16 | character, offset). A
# character is six 16-bit values (advance width, packed size, bitmap width,
# bitmap height, origin x, origin y) and its packed pixels:
#
#   00 hi lo   one pixel, ARGB4444; its colour stays current for what follows
#   01..3f     that many transparent pixels
#   41..7f     (byte & 3f) opaque pixels of the current colour
#   80..bf     10aaa000: one pixel of the current colour, alpha a/7
#              (the other low bits add a run; not written here)
#   c0..ff     11aaabbb: two pixels of the current colour, alphas a/7 and b/7
#
# Each Xbox glyph is overwritten in place by a DualSense one with the same
# metrics, so nothing else in the file moves; a glyph that would not fit in
# the bytes of the one it replaces is left alone.

FONT_PACKAGE = os.path.join('maps', 'fonts', 'font_package.bin')
RING = (214, 218, 226)
DISC = (38, 40, 48)


def _font_face(symbol, colour):
    def make(w, filled):
        cx, r = w / 2.0, min(w, 100) / 2.0 - 5
        layers = [(_disc((cx, 50), r), DISC)] if filled else []
        return layers + [(_outline(_disc((cx, 50), r), 8), RING), (symbol(cx), colour)]
    return make


def _font_label(label, radius):
    def make(w, filled):
        cx = w / 2.0
        half = (min(cx - 4, 54), 38)
        return [(_outline(_box((cx, 50), half, radius), 8), WHITE),
                (_text(label, (cx, 51), 40, 9), WHITE)]
    return make


def _font_stick(label):
    def make(w, filled):
        cx = w / 2.0
        return [(_outline(_disc((cx, 50), 43), 8), WHITE),
                (_text(label, (cx, 51), 44 if len(label) == 1 else 34, 9), WHITE)]
    return make


def _font_plain(layers):
    def make(w, filled):
        dx = w / 2.0 - 50
        return [(lambda p, f=f: f((p[0] - dx, p[1])), colour) for f, colour in layers()]
    return make


# character -> (PS5 name, drawing for a bitmap 100 high and w wide)
FONT_GLYPHS = {
    0xE100: ('Cross', _font_face(lambda cx: lambda p: min(
        _line([(cx - 18, 32), (cx + 18, 68)], 10)(p), _line([(cx - 18, 68), (cx + 18, 32)], 10)(p)),
        (124, 178, 232))),
    0xE101: ('Circle', _font_face(lambda cx: _outline(_disc((cx, 50), 19), 10), (255, 102, 102))),
    0xE102: ('Square', _font_face(lambda cx: _outline(_box((cx, 50), (17, 17), 2), 10), (234, 130, 220))),
    0xE103: ('Triangle', _font_face(lambda cx: _line(
        [(cx, 27), (cx + 22, 64), (cx - 22, 64)], 10, closed=True), (64, 226, 160))),
    0xE104: ('L1', _font_label('L1', 14)),
    0xE105: ('R1', _font_label('R1', 14)),
    0xE106: ('L2', _font_label('L2', 26)),
    0xE107: ('R2', _font_label('R2', 26)),
    0xE10C: ('Options', _font_plain(_options)),
    0xE10D: ('Create', _font_plain(_create)),
    0xE10E: ('L3', _font_stick('L3')),
    0xE10F: ('R3', _font_stick('R3')),
    0xE110: ('L', _font_stick('L')),
    0xE111: ('R', _font_stick('R')),
    0xE133: ('L', _font_stick('L')), 0xE134: ('L', _font_stick('L')), 0xE135: ('L', _font_stick('L')),
    0xE136: ('R', _font_stick('R')), 0xE137: ('R', _font_stick('R')), 0xE138: ('R', _font_stick('R')),
}


def pack_pixels(pixels):
    """Font-package pixel data for a list of (r, g, b, a), 0..255."""
    quads = [((a * 15 + 127) // 255, (r * 15 + 127) // 255, (g * 15 + 127) // 255,
              (b * 15 + 127) // 255) for r, g, b, a in pixels]
    out, i, n, current = bytearray(), 0, len(quads), None
    while i < n:
        a, rgb = quads[i][0], quads[i][1:]
        if a == 0:
            j = i
            while j < n and quads[j][0] == 0 and j - i < 0x3f:
                j += 1
            out.append(j - i)
            i = j
        elif rgb != current:
            out += bytes((0, a << 4 | rgb[0], rgb[1] << 4 | rgb[2]))
            current = rgb
            i += 1
        elif a == 15:
            j = i
            while j < n and quads[j] == quads[i] and j - i < 0x3f:
                j += 1
            out.append(0x40 | (j - i))
            i = j
        else:
            a3 = (a * 7 + 7) // 15
            nxt = quads[i + 1] if i + 1 < n else None
            if nxt and (nxt[0] == 0 or nxt[1:] == current):
                out.append(0xc0 | a3 << 3 | (nxt[0] * 7 + 7) // 15)
                i += 2
            else:
                out.append(0x80 | a3 << 3)
                i += 1
    return bytes(out)


def unpacked_length(data):
    """How many pixels font-package pixel data holds, or -1 if it is cut short."""
    runs = (0, 4, 3, 2, 5, 4, 3, 2)
    count, i = 0, 0
    while i < len(data):
        b = data[i]
        i += 1
        if b == 0:
            i += 2
            count += 1
        elif b < 0x80:
            count += b & 0x3f
        elif b < 0xc0:
            count += 1 + runs[b & 7]
        else:
            count += 2
    return count if i == len(data) else -1


def ps5_font_package(data):
    """(patched font package, glyphs replaced, glyphs left alone), or None if
    the file is not laid out as expected."""
    if len(data) < 0x10000 or len(data) % 0x8000 or data[:4] != b'\x03\x00\x00\xc0':
        return None
    packages = struct.unpack_from('<I', data, 0x114)[0]
    if (packages + 1) * 0x8000 != len(data):
        return None
    found, left = {}, 0                                  # font -> [(place, size, w, h, glyph)]
    for package in range(1, packages + 1):
        base = package * 0x8000
        table, count = struct.unpack_from('<HH', data, base)
        if table + 8 * count > 0x8000:
            return None
        for n in range(count):
            key, offset = struct.unpack_from('<II', data, base + table + 8 * n)
            glyph = FONT_GLYPHS.get(key & 0xffff)
            if not glyph:
                continue
            at = base + offset
            if offset + 12 > 0x8000:
                return None
            size, w, h = struct.unpack_from('<Hhh', data, at + 2)
            if (offset + 12 + size > 0x8000 or not 8 <= w <= 128 or not 8 <= h <= 128
                    or unpacked_length(data[at + 12:at + 12 + size]) != w * h):
                left += 1
                continue
            found.setdefault(key >> 16, []).append((at, size, w, h, glyph))

    out, done, drawn = bytearray(data), 0, {}

    def packed(glyph, w, h, filled):
        if (glyph[0], w, h, filled) not in drawn:
            layers = glyph[1](100.0 * w / h, filled)
            drawn[glyph[0], w, h, filled] = pack_pixels(_raster(layers, w, h, 100.0 * w / h, 100.0))
        return drawn[glyph[0], w, h, filled]

    for glyphs in found.values():
        # filled face buttons pack bigger; a font gets them only if all of its fit
        filled = all(len(packed(glyph, w, h, True)) <= size for at, size, w, h, glyph in glyphs)
        for at, size, w, h, glyph in glyphs:
            new = packed(glyph, w, h, filled)
            if len(new) > size:
                left += 1
                continue
            struct.pack_into('<H', out, at + 2, len(new))
            out[at + 12:at + 12 + size] = new + bytes(size - len(new))
            done += 1
    return bytes(out), done, left


def patch_font_package(folder):
    path = os.path.join(folder, FONT_PACKAGE)
    if not os.path.isfile(path):
        return 'game menu glyphs: %s not found, skipped' % FONT_PACKAGE
    with open(path, 'rb') as f:
        current = f.read()
    original = current
    if os.path.exists(path + KEPT):                      # always start from the Xbox file
        with open(path + KEPT, 'rb') as f:
            original = f.read()
    result = ps5_font_package(original)
    if result is None or not result[1]:
        return 'game menu glyphs: %s is not as expected, left alone' % FONT_PACKAGE
    new, done, left = result
    if new == current:
        return 'game menu glyphs: already PS5'
    _keep_and_write(path, new)
    msg = ('game menu glyphs: %d glyphs replaced with PS5 ones in the game\'s fonts '
           '(original kept as font_package.bin%s)' % (done, KEPT))
    return msg + ('; %d left alone' % left if left else '')


# --- PS5 button glyphs in the fonts of mods ------------------------------------
#
# A mod's .pak holds a font package of its own, which the game uses instead of
# font_package.bin while the mod is loaded, and which may redraw the button
# characters at other sizes. The .pak's hash covers it, and the hash is how
# the game and servers tell mods apart, so the file is left as it is. The
# bridge redraws the glyphs in memory instead, in each part of a font as the
# game loads it (dewfont.c), when this file is in the game folder.

GLYPH_SWITCH = 'dewbridge_ps5_glyphs.txt'
GLYPH_SWITCH_TEXT = (b'While this file is here, the bridge (binkw32.dll) draws PS5 button glyphs\r\n'
                     b'into the fonts the game loads, those of mods included. Made by patch_for_ps5.py.\r\n')


def patch_bridge_glyphs(folder):
    path = os.path.join(folder, GLYPH_SWITCH)
    if os.path.isfile(path):
        return 'mod font glyphs: already switched on'
    with open(path, 'wb') as f:
        f.write(GLYPH_SWITCH_TEXT)
    return 'mod font glyphs: the bridge will draw PS5 glyphs into fonts as they load (%s)' % GLYPH_SWITCH


def undo_bridge_glyphs(folder):
    path = os.path.join(folder, GLYPH_SWITCH)
    if not os.path.isfile(path):
        return 'mod font glyphs: not switched on, left alone'
    os.remove(path)
    return 'mod font glyphs: switched off (%s removed)' % GLYPH_SWITCH


# --- PS5 names and picture in Settings > Controls -----------------------------
#
# The controller tab lists the buttons by their Xbox names in every binding
# drop-down, and shows a photo of an Xbox One pad with lines out to the labels.
# The names are changed where they are displayed only: the values the page
# sends to the game stay "A", "LB", ... The photo is replaced by one of a
# DualSense (dualsense_controller.png next to this script, built by
# make_controller_pic.py). A DualSense has its d-pad and left stick the other
# way round and its Options button on the right, so some labels also change
# places in settings.css to keep the lines from crossing.

SETTINGS_JS = os.path.join('ui', 'screens', 'settings', 'settings.js')
NAME_OLD = b'opt.textContent = buttons[x];'
NAME_NEW = (b"opt.textContent = ({A:'Cross',B:'Circle',X:'Square',Y:'Triangle',"
            b"RB:'R1',LB:'L1',LT:'L2',RT:'R2',Start:'Options',Back:'Create',"
            b"LS:'L3',RS:'R3'})[buttons[x]] || buttons[x];")

CONTROLLER_PIC = os.path.join('ui', 'assets', 'settings', 'controller.png')
CONTROLLER_SRC = os.path.join(HERE, 'dualsense_controller.png')
SETTINGS_CSS = os.path.join('ui', 'screens', 'settings', 'settings.css')
LABELS_MARK = b'/* patch_for_ps5: controller labels placed for the DualSense picture */'
# label -> the label whose place on the page it takes
LABEL_MOVES = {'Back': 'Start', 'Up': 'Back', 'Left': 'LS', 'Down': 'Up', 'Right': 'Left',
               'LS': 'Down', 'RS': 'Right', 'Start': 'X', 'X': 'RS'}


def move_labels(css):
    """settings.css with the label rules swapped round, or None if it is not
    laid out as expected."""
    rules = {}
    for name in LABEL_MOVES:
        found = list(re.finditer(rb'(?m)^#' + name.encode() + rb'[ \t]*\{([^{}]*)\}', css))
        if len(found) != 1:
            return None
        rules[name] = found[0]
    out, pos = [LABELS_MARK, b'\r\n' if b'\r\n' in css else b'\n'], 0
    for name, m in sorted(rules.items(), key=lambda item: item[1].start()):
        out += [css[pos:m.start(1)], rules[LABEL_MOVES[name]].group(1)]
        pos = m.end(1)
    return b''.join(out) + css[pos:]


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
    css_path = os.path.join(folder, SETTINGS_CSS)
    for rel in (CONTROLLER_PIC, SETTINGS_CSS):
        if not os.path.isfile(os.path.join(folder, rel)):
            return 'controller picture: %s not found, skipped' % rel
    source = os.path.join(GLYPH_OVERRIDES, 'controller.png')
    if not os.path.isfile(source):
        source = CONTROLLER_SRC
    if not os.path.isfile(source):
        return 'controller picture: dualsense_controller.png is not next to this script, skipped'
    with open(source, 'rb') as f:
        new = f.read()
    with open(path, 'rb') as f:
        data = f.read()
    with open(css_path, 'rb') as f:
        css = f.read()

    # the picture and the label places go together: both or neither
    if LABELS_MARK in css:
        new_css = css
    else:
        new_css = move_labels(css)
        if new_css is None:
            return 'controller picture: %s is not as expected, picture left alone' % SETTINGS_CSS
    if data == new and new_css == css:
        return 'controller picture: already PS5'
    if data != new:
        _keep_and_write(path, new)
    if new_css != css:
        _keep_and_write(css_path, new_css)
    return ('controller picture: DualSense photo, labels moved to match '
            '(originals kept as controller.png%s, settings.css%s)' % (KEPT, KEPT))


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
    out.append(undo_kept(folder, FONT_PACKAGE, 'game menu glyphs'))
    out.append(undo_bridge_glyphs(folder))
    out.append(undo_kept(folder, SETTINGS_JS, 'button names'))
    out.append(undo_kept(folder, CONTROLLER_PIC, 'controller picture'))
    out.append(undo_kept(folder, SETTINGS_CSS, 'controller labels'))
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
            lines += [patch_glyphs(folder), patch_font_package(folder), patch_bridge_glyphs(folder),
                      patch_button_names(folder), patch_controller_pic(folder)]
    for line in lines:
        print('  ' + line)
    if not args.undo:
        print('In Playden, set the program arguments to: --single-process --in-process-gpu')


if __name__ == '__main__':
    main()
