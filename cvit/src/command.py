from cpu6asm import Asm
from cvit.constants import COMMAND_LOAD
from cvit.src.hawk import emit_hawk_read, emit_hawk_waits


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

    a.label("sta_native")
    a.print("\r\nCPU6\r\n")
    a.print("MEM  128K\r\n\r\n")
    a.print("DISKS\r\n")
    a.print(" F0:  8\" FLOPPY   EMPTY\r\n")
    a.print(" F1:  8\" FLOPPY   EMPTY\r\n")
    a.print(" H0:  HAWK        READY  CVIT\r\n")
    a.print(" H1:  HAWK        EMPTY\r\n")
    a.print("\r\nTERMINALS\r\n")
    a.print(" T0:  CONSOLE     9600\r\n")
    a.print(" T1:  MUX1        9600\r\n")
    a.print(" T2:  MUX2        OFFLINE\r\n")
    a.print(" T3:  MUX3        OFFLINE\r\n")
    a.rsr()

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
