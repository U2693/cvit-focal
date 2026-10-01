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

a.label("cold_start")
a.print("\r\nPRODOS-6 V0.1\r\n")
a.print("COPYRIGHT (C) 2026 BISCVIT\r\n")
a.print("\r\n/SYSTEM\r\n")
a.print("]CAT\r\n")
a.print("\r\nNAME       TYPE\r\n")
a.print("KERNEL     SYS\r\n")
a.print("COMMAND    SYS\r\n")
a.print("BASIC      SYS\r\n")
a.print("\r\n]RUN COMMAND\r\n")
a.print("COMMAND NOT LOADED YET\r\n")
a.label("prompt")
a.print("]")
a.hlt().jmp("prompt")

a.label("warm_start")
a.print("\r\n]").hlt().jmp("warm_start")

a.label("quit")
a.print("\r\nBYE\r\n").hlt().jmp("quit")

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
