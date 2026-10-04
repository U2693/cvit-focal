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
OS_ROOT = root / "os"
SYSTEM_ROOT = OS_ROOT / "SYSTEM"
HELP_ROOT = OS_ROOT / "HELP"
SYSTEM_ROOT.mkdir(parents=True, exist_ok=True)
HELP_ROOT.mkdir(parents=True, exist_ok=True)


def alloc_pages(data_len):
    """SYSTEM library page allocation increment used by mkhawk.py."""
    return max(2, ((data_len + PAGE - 1) // PAGE + 1) & ~1)


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
    base = 0x2000 + (row & 0xFF80)
    off = row & 0x7F
    a.lda_i(base).xaz()
    for i in range(10):
        a.ldab_z(off + i).ldbb_i(0x7F).andb_bl_al().xfrb_al_bl().stbb_d(0xF201)
    a.print(f" {typ}\r\n")


def emit_cat_rows(a):
    """Emit CAT rows from SYSTEM page 0 until the 84 8D terminator."""
    for row in range(16, 200, 16):
        cont = f"cat_row_{row:02x}"
        base = 0x2000 + (row & 0xFF80)
        off = row & 0x7F
        a.lda_i(base).xaz()
        a.ldab_z(off).ldbb_i(0x84).sabb().bnz(cont)
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
    cmp_al('P', "cmd_prefix"); cmp_al('p', "cmd_prefix")
    cmp_al('R', "cmd_run"); cmp_al('r', "cmd_run")
    cmp_al('Q', "cmd_quit"); cmp_al('q', "cmd_quit")
    cmp_al('.', "cmd_dot")
    a.jsr_abs("drain_line")
    a.print("?SYNTAX\r\n")
    a.jmp_abs("prompt")

    a.label("cmd_dot")
    a.jsr_abs("getc_echo")
    cmp_al('S', "cmd_sta"); cmp_al('s', "cmd_sta")
    cmp_al('D', "cmd_debug"); cmp_al('d', "cmd_debug")
    cmp_al('C', "cmd_ced"); cmp_al('c', "cmd_ced")
    cmp_al('K', "cmd_keys"); cmp_al('k', "cmd_keys")
    a.jsr_abs("drain_line")
    a.print("?SYNTAX\r\n")
    a.jmp_abs("prompt")

    a.label("cmd_help")
    a.jsr_abs("drain_line")
    a.print("COMMANDS: CAT, TYPE WELCOME, RUN NAME, PREFIX, HELP, .STA, .DEBUG, .CED, QUIT\r\n")
    a.jmp_abs("prompt")

    a.label("cmd_sta")
    a.jsr_abs("drain_line")
    a.svc(0x53)
    a.jmp_abs("prompt")

    a.label("cmd_ced")
    a.jsr_abs("ced_line_start")
    a.jmp_abs("prompt")

    a.label("cmd_keys")
    a.jsr_abs("drain_line")
    a.svc(0x54)
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
    a.jsr_abs("cat_line")
    a.jmp_abs("prompt")

    a.label("cmd_type")
    a.jsr_abs("type_line")
    a.jmp_abs("prompt")

    a.label("cmd_prefix")
    a.jsr_abs("prefix_line")
    a.jmp_abs("prompt")

    a.label("cmd_run")
    a.jsr_abs("run_line")
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

    def ced_line_reader(label, svc):
        buf = 0x2F00
        end = f"{label}_end"
        a.label(label)
        for i in range(32):
            a.ldab_i(0x0D).stab_d(buf + i)
        for i in range(32):
            cont = f"{label}_cont_{i}"
            a.jsr_abs("getc_echo")
            a.stab_d(buf + i)
            a.ldbb_i(0x0D).sabb().bnz(cont)
            a.jmp_abs(end)
            a.label(cont)
        a.jsr_abs("drain_line")
        a.label(end)
        a.svc(svc)
        a.rsr()

    debug_line_reader("debug_line_dump", 0x42)
    debug_line_reader("debug_line_unasm", 0x43)
    debug_line_reader("debug_line_deposit", 0x44)
    ced_line_reader("type_line", 0x51)
    ced_line_reader("cat_line", 0x52)
    ced_line_reader("prefix_line", 0x55)
    ced_line_reader("run_line", 0x56)
    ced_line_reader("ced_line_start", 0x50)

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
    a.stb_d(0x2EFE)          # SVC $40 ABI: AX=function, BX=control block pointer.
    a.ldbb_i(1).sabb().bnz("syscall_unimpl")
    a.ldb_d(0x2EFE).ldab_bx(0).stab_d(0xF201).rsr()  # function 1: putc, CB+0 = char.
    a.label("syscall_unimpl")
    a.ldb_d(0x2EFE).print("\r\n?SVC\r\n").rsr()

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


def member_name(path):
    n = path.stem.upper()
    assert 0 < len(n) <= 10, f"bad member name {path.name}: {n}"
    return n


def collect_members(generated):
    """Return mkhawk SYSTEM members from every file in ./os/SYSTEM, with boot-critical order."""
    files = {member_name(p): p for p in SYSTEM_ROOT.iterdir() if p.is_file()}
    for fname in generated:
        files[member_name(Path(fname))] = SYSTEM_ROOT / fname
    names = set(files)
    priority = ["KERNEL", "WELCOME", "BASIC", "CED", "TEST", "ZEP"]
    ordered = [n for n in priority if n in names]
    ordered += sorted(n for n in names if n not in set(priority) | {"COMMAND"})
    if "COMMAND" in names:
        ordered.append("COMMAND")
    members = []
    for n in ordered:
        p = files[n]
        data = generated.get(p.name, p.read_bytes())
        members.append((n, p, data))
    return members


def member_pages(members):
    pages, start = {}, 2
    for n, _p, data in members:
        pages[n] = start
        start += alloc_pages(len(data))
    return pages


basic_placeholder = b"CV\x00\x20\x00\x20\x00\x00BASIC placeholder\r" * 8
ced_placeholder = b"CV\x00\x20\x00\x20\x00\x00CED is resident in COMMAND via SVC $50\r" * 4
test_placeholder = b"TEST is a preallocated cvit CED save target.\r".ljust(400, b" ")
zep_placeholder = b"ZEP is a preallocated cvit CED save target.\r".ljust(400, b" ")

# Multi-pass the literals that depend on SYSTEM member placement.  Instruction
# widths are fixed, so later passes preserve the computed layout.  All files in
# ./os/SYSTEM files are included as SYSTEM members; generated files override
# their on-disk contents for this build.  ./os/HELP is reserved for the next
# library once cvit grows multi-library image generation.
command = build_command(0)
command_sectors = -(-len(command) // 400)
kernel = build_kernel(0, command_sectors)
welcome_sector = command_sector = 0
for _ in range(6):
    generated = {
        "kernel.bin": kernel,
        "welcome.txt": WELCOME_TEXT,
        "basic.bin": basic_placeholder,
        "ced.bin": ced_placeholder,
        "test.txt": test_placeholder,
        "zep.txt": zep_placeholder,
        "command.bin": command,
    }
    members = collect_members(generated)
    pages = member_pages(members)
    new_welcome_sector = DATA + pages["WELCOME"] // 2
    new_command_sector = DATA + pages["COMMAND"] // 2
    new_command = build_command(new_welcome_sector)
    new_command_sectors = -(-len(new_command) // 400)
    new_kernel = build_kernel(new_command_sector, new_command_sectors)
    if (new_welcome_sector == welcome_sector and new_command_sector == command_sector and
            new_command == command and new_kernel == kernel and new_command_sectors == command_sectors):
        break
    welcome_sector, command_sector = new_welcome_sector, new_command_sector
    command, kernel, command_sectors = new_command, new_kernel, new_command_sectors
else:
    raise RuntimeError("layout did not converge")

generated = {
    "kernel.bin": kernel,
    "welcome.txt": WELCOME_TEXT,
    "basic.bin": basic_placeholder,
    "ced.bin": ced_placeholder,
    "test.txt": test_placeholder,
    "zep.txt": zep_placeholder,
    "command.bin": command,
}
for fname, data in generated.items():
    (SYSTEM_ROOT / fname).write_bytes(data)
members = collect_members(generated)
(root / "out").mkdir(exist_ok=True)
cmd = [sys.executable, str(root / "scripts/mkhawk.py"), str(root / "out/os.img"), "--force"]
for n, p, _data in members:
    cmd += ["--member", f"{n}={p}"]
subprocess.check_call(cmd)
print("SYSTEM members:", ", ".join(n for n, _p, _data in members))
print(f"WELCOME at sector 0x{welcome_sector:04X}; COMMAND at sector 0x{command_sector:04X}+{command_sectors} -> 0x{COMMAND_LOAD:04X}")
