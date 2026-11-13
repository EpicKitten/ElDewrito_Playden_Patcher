#!/bin/sh
# Build dewbridge as a stand-in for binkw32.dll (32-bit, no C runtime).
# usage: build.sh /path/to/original/binkw32.dll
set -e
cd "$(dirname "$0")"
orig="$1"

# kernel32 import library
cat > kernel32.def <<'EOF'
LIBRARY KERNEL32.dll
EXPORTS
GetModuleHandleA@4
GetProcAddress@8
VirtualProtect@16
OutputDebugStringA@4
CreateFileA@28
WriteFile@20
SetFilePointer@16
CloseHandle@4
EOF
llvm-dlltool-18 -m i386 -k -d kernel32.def -l kernel32.lib

# every Bink export, forwarded to binkw32_orig.dll, with its original ordinal
python3 - "$orig" > exports.rsp <<'EOF'
import struct, sys
d = open(sys.argv[1], 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]
optsz = struct.unpack_from('<H', d, pe + 20)[0]
opt = pe + 24
secs = [struct.unpack_from('<IIII', d, opt + optsz + i * 40 + 8) for i in range(nsec)]
def off(r):
    for vsz, va, rsz, raw in secs:
        if va <= r < va + max(vsz, rsz):
            return raw + (r - va)
e = off(struct.unpack_from('<I', d, opt + 96)[0])
base = struct.unpack_from('<I', d, e + 16)[0]
nnames = struct.unpack_from('<I', d, e + 24)[0]
afun, anames, aord = struct.unpack_from('<III', d, e + 28)
for i in range(nnames):
    n = off(struct.unpack_from('<I', d, off(anames) + 4 * i)[0])
    name = d[n:d.index(b'\0', n)].decode('latin1')
    o = struct.unpack_from('<H', d, off(aord) + 2 * i)[0] + base
    print('/export:%s=binkw32_orig.%s,@%d' % (name, name, o))
EOF

clang-18 -target i686-pc-windows-msvc -std=c11 -Os -ffreestanding -fno-builtin \
	-fno-stack-protector -mno-stack-arg-probe -Wall -Wextra -c dewbridge.c -o dewbridge.obj
lld-link-18 /dll /machine:x86 /nodefaultlib /entry:DllMain /safeseh:no /out:binkw32.dll \
	dewbridge.obj kernel32.lib @exports.rsp
ls -l binkw32.dll
