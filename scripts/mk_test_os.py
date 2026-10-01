#!/usr/bin/env python3
"""Generate ProDOS-6 placeholder KERNEL/BASIC/COMMAND files and build out/os.img."""
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from cpu6asm import Asm

root = Path(__file__).parent.parent
(root / "os").mkdir(exist_ok=True)

# SYSTEM/KERNEL: first ProDOS-6 personality stub.  It deliberately starts with a
# 3-byte absolute-jump table so future COMMAND/BASIC binaries have stable entry
# points even while internals move around.
a = Asm(0x0800)
for vector in [
    "cold_start", "warm_start", "syscall", "quit", "read_block", "write_block",
    "open", "close", "read", "write", "get_file_info", "set_file_info",
    "create", "destroy", "rename", "set_prefix", "get_prefix",
]:
    a.jmp_abs(vector)

def emit_member(row):
    """Print one 16-byte SYSTEM library row from the cached directory sector."""
    a.lda_i(0x2000).xaz()
    for i in range(10):
        a.ldab_z(row + i).ldbb_i(0x7F).andb_bl_al().xfrb_al_bl().stbb_d(0xF201)
    a.print(" SYS\r\n")


def emit_cat_rows():
    """Emit CAT rows from SYSTEM page 0 until the 84 8D terminator."""
    for row in range(16, 200, 16):
        cont = f"cat_row_{row:02x}"
        a.lda_i(0x2000).xaz()
        a.ldab_z(row).ldbb_i(0x84).sabb().bnz(cont)
        a.jmp_abs("cat_done")
        a.label(cont)
        emit_member(row)
    a.label("cat_done")


a.label("cold_start")
a.print("\r\nPRODOS-6 V0.1\r\n")
a.print("COPYRIGHT (C) 2026 BISCVIT\r\n")
a.jsr_abs("read_system_dir")
a.print("\r\n/SYSTEM\r\n")
a.print("]CAT\r\n")
a.print("\r\nNAME       TYPE\r\n")
# CAT is now backed by the SYSTEM library directory sector read from Hawk.
emit_cat_rows()
a.print("\r\n]RUN COMMAND\r\n")
a.print("COMMAND NOT LOADED YET\r\n")
a.label("prompt")
a.print("]")
a.hlt().jmp("prompt")

a.label("warm_start")
a.print("\r\n]").hlt().jmp("warm_start")

a.label("quit")
a.print("\r\nBYE\r\n").hlt().jmp("quit")

# Read SYSTEM library directory sector (logical sector 0x20) to 0x2000.  This is
# the first real CAT plumbing; it uses the same Hawk/DMA sequence as stage 1.
a.label("read_system_dir")
a.lda_i(0x2000).dma_sad_a()
a.lda_i(0xFE6F).dma_sct_a()      # -401 -> 400 bytes
a.dma_sdv_0().dma_eab()
a.lda_i(0xF140).xaz()            # Z = Hawk registers
a.jsr("hawk_ready")
a.lda_i(0x0020).ldb_i(0x3FFF).nab().stb_z(1)   # F141/F142 = sector address
a.ldab_i(2).stab_z(8)            # seek
a.jsr("hawk_ready")
a.ldab_i(0).stab_z(8)            # read
a.jsr("hawk_busy")
a.xfrb_au_al().bnz("hawk_error") # AU = F144 status byte
a.rsr()
a.label("hawk_busy")
a.ldab_z(4).srab().bl("hawk_busy")
a.label("hawk_ready")
a.lda_z(4).ldbb_i(0x30).andb_bl_al().sabb().bnz("hawk_ready").rsr()
a.label("hawk_error")
a.print("\r\nHAWK READ ERROR\r\n").hlt().jmp("hawk_error")

# Bring-up stubs for the future MLI-ish API.  Returning is friendlier for calls;
# direct jumps still make the missing vector visible.
for vector in [
    "syscall", "read_block", "write_block", "open", "close", "read", "write",
    "get_file_info", "set_file_info", "create", "destroy", "rename",
    "set_prefix", "get_prefix",
]:
    a.label(vector).print("\r\n?UNIMPL\r\n").rsr()

(root / "os/kernel.bin").write_bytes(a.bytes())

# Placeholder members for the SYSTEM library.  These are not loadable yet; the
# kernel's next milestone is to read the library and run COMMAND.
(root / "os/basic.bin").write_bytes(b"P6\x00\x20\x00\x20\x00\x00BASIC placeholder\r" * 8)
(root / "os/command.bin").write_bytes(b"P6\x00\x20\x00\x20\x00\x00COMMAND placeholder\r" * 8)
(root / "out").mkdir(exist_ok=True)
subprocess.check_call([sys.executable, str(root / "scripts/mkhawk.py"), str(root / "out/os.img"), "--force",
    "--member", f"KERNEL={root}/os/kernel.bin", "--member", f"BASIC={root}/os/basic.bin",
    "--member", f"COMMAND={root}/os/command.bin"])
