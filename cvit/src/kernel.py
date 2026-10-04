from cpu6asm import Asm
from cvit.constants import COMMAND_LOAD
from cvit.src.disk6 import emit_disk6_read_block
from cvit.src.hawk import emit_hawk_read, emit_hawk_waits


def build_kernel(command_sector, command_sectors=1):
    # SYSTEM/KERNEL: stable jump table plus a cold start that loads COMMAND.
    a = Asm(0x0800)
    for vector in [
        "cold_start", "warm_start", "syscall", "quit", "read_block", "write_block",
        "open", "close", "read", "write", "get_file_info", "set_file_info",
        "create", "destroy", "rename", "set_prefix", "get_prefix",
    ]:
        a.jmp_abs(vector)

    a.label("cold_start")
    a.print("\r\ncvit V0.1\r\n")
    a.print("COPYRIGHT (C) 2026 BISCVIT\r\n")
    a.jsr_abs("load_command")
    a.lda_i(COMMAND_LOAD).xay().jmp_y()

    a.label("warm_start")
    a.lda_i(COMMAND_LOAD).xay().jmp_y()

    a.label("quit")
    a.print("\r\nBYE\r\n").hlt().jmp("quit")

    a.label("syscall")
    a.stb_d(0x2EFE)          # SVC $40 ABI: AX=function, BX=control block pointer.
    a.ldbb_i(1).sabb().bnz("syscall_not_putc")
    a.ldb_d(0x2EFE).ldab_bx(0).stab_d(0xF201).rsr()  # function 1: putc, CB+0 = char.
    a.label("syscall_not_putc")
    a.ldbb_i(2).sabb().bnz("syscall_unimpl")
    a.ldb_d(0x2EFE).jmp_abs("read_block")             # function 2: Disk6 read_block.
    a.label("syscall_unimpl")
    a.ldb_d(0x2EFE).print("\r\n?SVC\r\n").rsr()

    a.label("load_command")
    for i in range(command_sectors):
        a.jsr_abs(f"load_command_{i}")
    a.rsr()
    for i in range(command_sectors):
        emit_hawk_read(a, f"load_command_{i}", command_sector + i, COMMAND_LOAD + 400 * i)
    emit_hawk_waits(a)
    emit_disk6_read_block(a)

    # Bring-up stubs for the future MLI-ish API.  Returning is friendlier for calls;
    # direct jumps still make the missing vector visible.
    for vector in [
        "write_block", "open", "close", "read", "write",
        "get_file_info", "set_file_info", "create", "destroy", "rename",
        "set_prefix", "get_prefix",
    ]:
        a.label(vector).print("\r\n?UNIMPL\r\n").rsr()

    return a.bytes()
