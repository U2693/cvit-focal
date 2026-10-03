#!/usr/bin/env python3
"""Generate cvit KERNEL/COMMAND test members and build out/os.img."""
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from cpu6asm import Asm

PAGE = 200
DATA = 0x20
COMMAND_LOAD = 0x3000
WELCOME_TEXT = b"WELCOME TO cvit\r\nTHIS TEXT WAS LOADED FROM /SYSTEM/WELCOME.\r\n"

root = Path(__file__).parent.parent
(root / "os").mkdir(exist_ok=True)


def alloc_pages(data_len):
    """SYSTEM library page allocation increment used by mkhawk.py."""
    return ((data_len + PAGE - 1) // PAGE + 1) & ~1


def emit_hawk_read(a, label, sector, dst):
    a.label(label)
    a.lda_i(dst).dma_sad_a()
    a.lda_i(0xFE6F).dma_sct_a()      # -401 -> 400 bytes
    a.dma_sdv_0().dma_eab()
    a.lda_i(0xF140).xaz()            # Z = Hawk registers
    a.jsr_abs("hawk_ready")
    a.lda_i(sector).ldb_i(0x3FFF).nab().stb_z(1)   # F141/F142 = sector address
    a.ldab_i(2).stab_z(8)            # seek
    a.jsr_abs("hawk_ready")
    a.ldab_i(0).stab_z(8)            # read
    a.jsr_abs("hawk_busy")
    ok = f"{label}_ok"
    a.xfrb_au_al().bz(ok)            # AU = F144 status byte
    a.jmp_abs("hawk_error")
    a.label(ok)
    a.rsr()


def emit_hawk_waits(a):
    a.label("hawk_busy")
    a.ldab_z(4).srab().bl("hawk_busy")
    a.label("hawk_ready")
    a.lda_z(4).ldbb_i(0x30).andb_bl_al().sabb().bnz("hawk_ready").rsr()
    a.label("hawk_error")
    a.print("\r\nHAWK READ ERROR\r\n").hlt().jmp("hawk_error")


def emit_member(a, row, typ="SYS"):
    """Print one 16-byte SYSTEM library row from the cached directory sector."""
    a.lda_i(0x2000).xaz()
    for i in range(10):
        a.ldab_z(row + i).ldbb_i(0x7F).andb_bl_al().xfrb_al_bl().stbb_d(0xF201)
    a.print(f" {typ}\r\n")


def emit_cat_rows(a):
    """Emit CAT rows from SYSTEM page 0 until the 84 8D terminator."""
    for row in range(16, 200, 16):
        cont = f"cat_row_{row:02x}"
        a.lda_i(0x2000).xaz()
        a.ldab_z(row).ldbb_i(0x84).sabb().bnz(cont)
        a.jmp_abs("cat_done")
        a.label(cont)
        emit_member(a, row, "TXT" if row == 32 else "SYS")
    a.label("cat_done")


def emit_cached_text(a, addr, length):
    a.lda_i(addr).xaz()
    for i in range(length):
        a.ldab_z(i).xfrb_al_bl().stbb_d(0xF201)


def build_command(welcome_sector):
    # SYSTEM/COMMAND: tiny interactive shell loaded at 0x3000 by KERNEL.
    a = Asm(COMMAND_LOAD)
    a.jmp_abs("start")

    cmp_id = {"n": 0}
    def cmp_al(ch, label):
        cmp_id["n"] += 1
        nxt = f"cmp_next_{cmp_id['n']}"
        a.ldbb_i(ord(ch)).sabb().bnz(nxt)
        a.jmp_abs(label)
        a.label(nxt)

    a.label("start")
    a.print("\r\ncvit COMMAND V0.1\r\n")
    a.print("TYPE HELP FOR COMMANDS\r\n")
    a.label("prompt")
    a.print("\r\n]")
    a.jsr_abs("getc_echo")
    a.ldbb_i(0x0D).sabb().bnz("not_blank")
    a.jmp_abs("prompt")
    a.label("not_blank")
    cmp_al('C', "cmd_cat"); cmp_al('c', "cmd_cat")
    cmp_al('T', "cmd_type"); cmp_al('t', "cmd_type")
    cmp_al('H', "cmd_help"); cmp_al('h', "cmd_help")
    cmp_al('Q', "cmd_quit"); cmp_al('q', "cmd_quit")
    cmp_al('.', "cmd_dot")
    a.jsr_abs("drain_line")
    a.print("?SYNTAX\r\n")
    a.jmp_abs("prompt")

    a.label("cmd_dot")
    a.jsr_abs("getc_echo")
    cmp_al('S', "cmd_sta"); cmp_al('s', "cmd_sta")
    cmp_al('D', "cmd_debug"); cmp_al('d', "cmd_debug")
    a.jsr_abs("drain_line")
    a.print("?SYNTAX\r\n")
    a.jmp_abs("prompt")

    a.label("cmd_help")
    a.jsr_abs("drain_line")
    a.print("COMMANDS: CAT, TYPE WELCOME, HELP, .STA, .DEBUG, QUIT\r\n")
    a.jmp_abs("prompt")

    a.label("cmd_sta")
    a.jsr_abs("drain_line")
    a.print("\r\nCPU6\r\n")
    a.print("MEM  128K\r\n\r\n")
    a.print("DISKS\r\n")
    a.print(" F0:  8\" FLOPPY   READY\r\n")
    a.print(" F1:  8\" FLOPPY   EMPTY\r\n")
    a.print(" D0:  HAWK        READY\r\n\r\n")
    a.print("TERMINALS\r\n")
    a.print(" T0:  CONSOLE     9600\r\n")
    a.print(" T1:  MUX1        OFFLINE\r\n")
    a.print(" T2:  MUX2        OFFLINE\r\n")
    a.print(" T3:  MUX3        OFFLINE\r\n")
    a.jmp_abs("prompt")

    a.label("cmd_debug")
    a.jsr_abs("drain_line")
    a.print("\r\ncvit DEBUG V0.1\r\n")
    a.print("COMMANDS: R X D U B S A Q\r\n")
    a.label("debug_prompt")
    a.print("\r\n:")
    a.jsr_abs("getc_echo")
    a.ldbb_i(0x0D).sabb().bnz("debug_not_blank")
    a.jmp_abs("debug_prompt")
    a.label("debug_not_blank")
    cmp_al('Q', "debug_quit"); cmp_al('q', "debug_quit")
    cmp_al('R', "debug_regs"); cmp_al('r', "debug_regs")
    cmp_al('X', "debug_dump"); cmp_al('x', "debug_dump")
    cmp_al('D', "debug_deposit"); cmp_al('d', "debug_deposit")
    cmp_al('U', "debug_unasm"); cmp_al('u', "debug_unasm")
    cmp_al('B', "debug_break"); cmp_al('b', "debug_break")
    cmp_al('S', "debug_step"); cmp_al('s', "debug_step")
    cmp_al('A', "debug_asm"); cmp_al('a', "debug_asm")
    a.jsr_abs("drain_line")
    a.print("?DEBUG\r\n")
    a.jmp_abs("debug_prompt")

    a.label("debug_regs")
    a.jsr_abs("drain_line")
    a.svc(0x41)
    a.jmp_abs("debug_prompt")

    a.label("debug_dump")
    a.jsr_abs("debug_line_dump")
    a.jmp_abs("debug_prompt")

    a.label("debug_unasm")
    a.jsr_abs("debug_line_unasm")
    a.jmp_abs("debug_prompt")

    a.label("debug_deposit")
    a.jsr_abs("debug_line_deposit")
    a.jmp_abs("debug_prompt")

    a.label("debug_break")
    a.jsr_abs("drain_line")
    a.print("BREAKPOINTS TODO\r\n")
    a.jmp_abs("debug_prompt")

    a.label("debug_step")
    a.jsr_abs("drain_line")
    a.print("SINGLE STEP TODO\r\n")
    a.jmp_abs("debug_prompt")

    a.label("debug_asm")
    a.jsr_abs("drain_line")
    a.print("MINI-ASSEMBLER TODO\r\n")
    a.jmp_abs("debug_prompt")

    a.label("debug_quit")
    a.jsr_abs("drain_line")
    a.print("LEAVING DEBUG\r\n")
    a.jmp_abs("prompt")

    a.label("cmd_cat")
    a.jsr_abs("drain_line")
    a.jsr_abs("read_system_dir")
    a.print("\r\nNAME       TYPE\r\n")
    emit_cat_rows(a)
    a.jmp_abs("prompt")

    a.label("cmd_type")
    a.jsr_abs("drain_line")
    a.jsr_abs("read_welcome")
    a.print("\r\n")
    emit_cached_text(a, 0x2200, len(WELCOME_TEXT))
    a.jmp_abs("prompt")

    a.label("cmd_quit")
    a.jsr_abs("drain_line")
    a.raw(0x71, 0x08, 0x09)  # JMP absolute kernel quit vector.

    def debug_line_reader(label, svc):
        buf = 0x2F00
        end = f"{label}_end"
        a.label(label)
        for i in range(8):
            a.ldab_i(0x0D).stab_d(buf + i)
        for i in range(8):
            a.jsr_abs("getc_echo")
            a.stab_d(buf + i)
            a.ldbb_i(0x0D).sabb().bz(end)
        a.jsr_abs("drain_line")
        a.label(end)
        a.svc(svc)
        a.rsr()

    debug_line_reader("debug_line_dump", 0x42)
    debug_line_reader("debug_line_unasm", 0x43)
    debug_line_reader("debug_line_deposit", 0x44)

    a.label("drain_line")
    a.jsr_abs("getc_echo")
    a.ldbb_i(0x0D).sabb().bnz("drain_line")
    a.rsr()

    a.label("getc_echo")
    a.jsr_abs("getc")
    a.ldbb_i(0x0D).sabb().bnz("not_cr_echo")
    a.jmp_abs("echo_cr")
    a.label("not_cr_echo")
    a.xfrb_al_bl().stbb_d(0xF201).rsr()
    a.label("echo_cr")
    a.print("\r\n")
    a.rsr()

    a.label("getc")
    a.label("getc_wait")
    a.ldab_d(0xF200).ldbb_i(1).andb_bl_al().bz("getc_wait")
    a.ldab_d(0xF201).ldbb_i(0x7F).andb_bl_al().rsr()

    emit_hawk_read(a, "read_system_dir", 0x0020, 0x2000)
    emit_hawk_read(a, "read_welcome", welcome_sector, 0x2200)
    emit_hawk_waits(a)
    return a.bytes()


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
    a.stab_d(0xF201).rsr()   # SVC $40 / JSR $0806: console putc from AL.

    a.label("load_command")
    for i in range(command_sectors):
        a.jsr_abs(f"load_command_{i}")
    a.rsr()
    for i in range(command_sectors):
        emit_hawk_read(a, f"load_command_{i}", command_sector + i, COMMAND_LOAD + 400 * i)
    emit_hawk_waits(a)

    # Bring-up stubs for the future MLI-ish API.  Returning is friendlier for calls;
    # direct jumps still make the missing vector visible.
    for vector in [
        "read_block", "write_block", "open", "close", "read", "write",
        "get_file_info", "set_file_info", "create", "destroy", "rename",
        "set_prefix", "get_prefix",
    ]:
        a.label(vector).print("\r\n?UNIMPL\r\n").rsr()

    return a.bytes()


# Multi-pass the literals that depend on SYSTEM member placement.  Instruction
# widths are fixed, so later passes preserve the computed layout.
command = build_command(0)
command_sectors = -(-len(command) // 400)
kernel = build_kernel(0, command_sectors)
welcome_page = 2 + alloc_pages(len(kernel))
welcome_sector = DATA + welcome_page // 2
command = build_command(welcome_sector)
assert command_sectors == -(-len(command) // 400)
basic_placeholder = b"CV\x00\x20\x00\x20\x00\x00BASIC placeholder\r" * 8
command_page = welcome_page + alloc_pages(len(WELCOME_TEXT)) + alloc_pages(len(basic_placeholder))
command_sector = DATA + command_page // 2
kernel = build_kernel(command_sector, command_sectors)
assert welcome_page == 2 + alloc_pages(len(kernel))

(root / "os/kernel.bin").write_bytes(kernel)
(root / "os/welcome.txt").write_bytes(WELCOME_TEXT)
(root / "os/basic.bin").write_bytes(basic_placeholder)
(root / "os/command.bin").write_bytes(command)
(root / "out").mkdir(exist_ok=True)
subprocess.check_call([sys.executable, str(root / "scripts/mkhawk.py"), str(root / "out/os.img"), "--force",
    "--member", f"KERNEL={root}/os/kernel.bin", "--member", f"WELCOME={root}/os/welcome.txt",
    "--member", f"BASIC={root}/os/basic.bin", "--member", f"COMMAND={root}/os/command.bin"])
print(f"WELCOME at sector 0x{welcome_sector:04X}; COMMAND at sector 0x{command_sector:04X}+{command_sectors} -> 0x{COMMAND_LOAD:04X}")
