"""Make ElDewrito 0.7.1's mtndew.dll use 0x400000 as the game's base address
instead of asking for a module snapshot result. Six sites; each must hold the
expected original bytes or nothing is written."""
import hashlib, os, shutil, struct, sys

dll = sys.argv[1]
exe = os.path.join(os.path.dirname(dll), 'eldorado.exe')

e = open(exe, 'rb').read(0x400)
pe = struct.unpack_from('<I', e, 0x3c)[0]
exe_base = struct.unpack_from('<I', e, pe + 24 + 28)[0]
print('eldorado.exe preferred base %x' % exe_base)
if exe_base != 0x400000:
    sys.exit('unexpected base, not patching')

# (va of "cmp edi,-1", va of "mov [cache],eax")
SITES = [
    (0x100eeb5a, 0x100eeb8f),
    (0x10153805, 0x10153840),
    (0x101538a2, 0x101538d9),
    (0x10153935, 0x1015396c),
    (0x101539ce, 0x10153a05),
    (0x101854de, 0x10185522),
]
ORIG = bytes.fromhex('83ffff75') # cmp edi,-1 ; jne
STORE = bytes.fromhex('a354683212')  # mov [0x12326854],eax


def off(va):
    return va - 0x10001000 + 0x400


d = bytearray(open(dll, 'rb').read())
print('before sha256', hashlib.sha256(d).hexdigest())
for cmp_va, store_va in SITES:
    o = off(cmp_va)
    if d[o:o + 4] != ORIG or d[o + 5:o + 7] != b'\x33\xc0':
        sys.exit('site %x does not match: %s' % (cmp_va, d[o:o + 9].hex()))
    if d[off(store_va):off(store_va) + 5] != STORE:
        sys.exit('store %x does not match' % store_va)
    rel = store_va - (cmp_va + 7)
    assert 0 < rel < 0x80
    d[o:o + 7] = b'\xb8' + struct.pack('<I', 0x400000) + b'\xeb' + bytes([rel])

bak = dll + '.orig'
if not os.path.exists(bak):
    shutil.copy2(dll, bak)
    print('backup written', bak)
open(dll, 'wb').write(d)
print('after  sha256', hashlib.sha256(d).hexdigest())
