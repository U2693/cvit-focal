#!/usr/bin/env python3
"""Stage 2 standalone FOCAL: Hawk IPL -> kernel -> FOCAL (no COMMAND).
Builds out/stage2.img with SYSTEM/KERNEL (stage-2 variant) and SYSTEM/FOCAL.
The variant kernel keeps the stock jump table and syscall stub; its block
vectors are Hawk (ME-2): read_block/write_block take a control block in
BX (+0 u16 sector, +2 u16 buffer) and return the Hawk status byte in AL.
Its cold start loads the FOCAL member at 0x5000 and JSRs to it; FOCAL
QUIT (RSR) returns into the kernel quit vector: BYE and halt. The member
blob is a 9-byte CV header + code; sectors are loaded to 0x5000-9 so the
code lands exactly at 0x5000. FOCAL console I/O is SVC 0x40 fn 1/2/3,
served by the host, or by the kernel JSYS door at 0x0100 under --bare-metal (ME-1)."""
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root)); sys.path.insert(0, str(root / "scripts"))
from cpu6asm import Asm
from cvit.constants import DATA
from cvit.image import collect_library_members, member_pages, pack_hawk_image, write_system_members
from cvit.src.hawk import emit_hawk_read, emit_hawk_read_block, emit_hawk_waits, emit_hawk_write_block
from cvit.src.fsload import emit_fs_load
from cvit.src.fssave import emit_fs_save, emit_fs_run, emit_fs_parse
from focal import build_focal
FOCAL_LOAD = 0x5000
HDR = 9
STAGE = root / "out" / "stage2-system"
OUT = root / "out" / "stage2.img"

def build_egg():
    load = 0x4000
    a = Asm(load)
    a.lda_label("msg").xaz().ldbb_i(2).svc(0x40).rsr()
    a.label("msg").raw(*b"HELLO FROM EGG\r\n\x00")
    code = a.bytes()
    return b"CV" + load.to_bytes(2, "big") * 2 + len(code).to_bytes(2, "big") + b"\x01" + code


def build_kernel2(focal_sector, focal_sectors):
    a = Asm(0x0800, page_safe=True)
    for v in ["cold_start", "warm_start", "syscall", "quit", "read_block", "write_block", "open", "close", "read", "write", "get_file_info", "set_file_info", "create", "destroy", "rename", "set_prefix", "get_prefix"]:
        a.jmp_abs(v)
    a.label("cold_start")
    a.lda_i(0x2E00).xfr("A", "S")  # stack to 0x2000: the ROM stack at 0x1000 now sits inside the grown kernel
    a.lda_i(0).ldab_d("door_b0").stab_d(0x0100)
    a.lda_i(0).ldab_d("door_b1").stab_d(0x0101)
    a.lda_i(0).ldab_d("door_b2").stab_d(0x0102)
    a.print("\r\ncvit V0.1\r\n")
    a.print("COPYRIGHT (C) 2026 BISCVIT\r\n")
    a.jsr_abs("load_focal")
    a.jsr_abs(FOCAL_LOAD)
    a.jmp_abs("quit")
    a.label("warm_start")
    a.jsr_abs(FOCAL_LOAD)
    a.jmp_abs("quit")
    a.label("quit")
    a.print("\r\nBYE\r\n").hlt().jmp("quit")
    a.label("syscall")
    a.stb_d(0x2EFE)
    a.ldbb_i(1).sabb().bnz("sc_not_putc")
    a.ldb_d(0x2EFE).ldab_bx(0).stab_d(0xF201).rsr()
    a.label("sc_not_putc")
    a.ldbb_i(2).sabb().bnz("sc_unimpl")
    a.ldb_d(0x2EFE).jmp_abs("read_block")
    a.label("sc_unimpl")
    a.ldb_d(0x2EFE).print("\r\n?SVC\r\n").rsr()
    # ME-1: JSYS dispatcher. Entered at the door (jmp_abs at 0x0100) with
    # the JSYS frame on the caller stack: [SP] = svc byte. Register ABI
    # per D1; private kernel stack per D3; polled console per D4.
    a.label("jsys_dispatch")
    a.stab_d("jd_tal").sta_d("jd_ta").stb_d("jd_tb")
    a.xfr("Z", "A").sta_d("jd_tz")
    a.xfr("Y", "A").sta_d("jd_ty")
    a.lda_i(0).ldab_x("S", disp=0).stab_d("jd_svc")
    a.xfr("S", "A").sta_d("jd_tsp")
    a.lda_i(0x2F40).xfr("A", "S")  # private kernel stack just below the FS workspace cells (0x2F40): NOT the FOCAL stack top (0x2E00) -- handler pushes must never reach the JSYS frame sitting on the caller stack just below its SP, or RSV pops a corrupted IPL and switches register banks
    a.lda_i(0).ldab_d("jd_svc").ldbb_i(0x40).sabb().bz("jd_console")
    a.lda_i(0).ldab_d("jd_svc").ldbb_i(0x57).sabb().bz("jd_load")
    a.lda_i(0).ldab_d("jd_svc").ldbb_i(0x58).sabb().bz("jd_save")
    a.lda_i(0).ldab_d("jd_svc").ldbb_i(0x56).sabb().bz("jd_run")
    a.jmp_abs("jd_unimpl")
    a.label("jd_console")
    a.ldb_d("jd_tb").xfrb_bl_al().ldbb_i(1).sabb().bz("jd_putc")
    a.ldb_d("jd_tb").xfrb_bl_al().ldbb_i(2).sabb().bz("jd_print")
    a.ldb_d("jd_tb").xfrb_bl_al().ldbb_i(3).sabb().bz("jd_getc")
    a.jmp_abs("jd_unimpl")
    a.label("jd_putc")
    a.lda_i(0).ldab_d(0xF200).ldbb_i(2).andb_bl_al().bz("jd_putc")
    a.lda_i(0).ldab_d("jd_tal").stab_d(0xF201)
    a.jmp_abs("jd_return")
    a.label("jd_print")
    a.lda_d("jd_tz").xaz()
    a.label("jd_p_loop")
    a.ldab_zinc().stab_d("jd_ch")
    a.lda_i(0).ldab_d("jd_ch").ldbb_i(0).sabb().bz("jd_return")
    a.label("jd_p_poll")
    a.lda_i(0).ldab_d(0xF200).ldbb_i(2).andb_bl_al().bz("jd_p_poll")
    a.lda_i(0).ldab_d("jd_ch").stab_d(0xF201)
    a.jmp_abs("jd_p_loop")
    a.label("jd_getc")
    a.lda_i(0).ldab_d(0xF200).ldbb_i(1).andb_bl_al().bz("jd_g_none")
    a.lda_i(0).ldab_d(0xF201).stab_d("jd_tal")
    a.jmp_abs("jd_return")
    a.label("jd_g_none")
    a.lda_i(0).stab_d("jd_tal")
    a.jmp_abs("jd_return")
    a.label("jd_unimpl")
    a.print("\r\n?SVC\r\n")
    a.jmp_abs("jd_return")
    a.label("jd_load")
    a.ldb_d("jd_tb").jmp_abs("fs_load")
    a.label("jd_save")
    a.ldb_d("jd_tb").jmp_abs("fs_save")
    a.label("jd_run")
    a.jmp_abs("fs_run")
    a.label("jd_return")
    a.lda_d("jd_tz").xaz()
    a.lda_d("jd_ty").xfr("A", "Y")
    a.ldb_d("jd_tb")
    a.lda_d("jd_tsp").xfr("A", "S")
    a.lda_d("jd_ta").ldab_d("jd_tal")
    a.raw(0x0F)  # RSV: unwind the JSYS frame
    a.label("load_focal")
    a.lda_i(focal_sector).sta_d("lf_sec")
    a.lda_i(FOCAL_LOAD - HDR).sta_d("lf_dst")
    a.lda_i(focal_sectors).sta_d("lf_cnt")
    a.label("lf_loop")
    a.lda_d("lf_cnt").ldb_i(0).sab().bz("lf_done")
    a.lda_d("lf_sec").sta_d("lf_cb")
    a.lda_d("lf_dst").sta_d("lf_cbb")
    a.lda_label("lf_cb").xfr("A", "B").jsr_abs(0x080C)
    a.ldbb_i(0).sabb().bnz("hawk_error")
    a.lda_d("lf_sec").ldb_i(1).aab().stb_d("lf_sec")
    a.lda_i(400).ldb_d("lf_dst").aab().stb_d("lf_dst")
    a.lda_d("lf_cnt").ldb_i(1).sab().stb_d("lf_cnt")
    a.jmp_abs("lf_loop")
    a.label("lf_done")
    a.rsr()
    a.align(0x1000)  # ROM boot stack writes below 0x1000: keep 0x0FE0-0x0FFF padding
    emit_hawk_waits(a)
    emit_hawk_read_block(a)
    emit_hawk_write_block(a)
    emit_fs_load(a)
    emit_fs_save(a)
    emit_fs_run(a)
    emit_fs_parse(a)
    for v in ["open", "close", "read", "write", "get_file_info", "set_file_info", "create", "destroy", "rename", "set_prefix", "get_prefix"]:
        a.label(v)
    a.print("\r\n?UNIMPL\r\n").rsr()
    a.label("door_b0").raw(0)
    a.label("door_b1").raw(0)
    a.label("door_b2").raw(0)
    a.label("jd_tal").raw(0)
    a.label("jd_svc").raw(0)
    a.label("jd_ch").raw(0)
    a.label("jd_ta").raw(0, 0)
    a.label("jd_tb").raw(0, 0)
    a.label("jd_tz").raw(0, 0)
    a.label("jd_tsp").raw(0, 0)
    a.label("jd_ty").raw(0, 0)
    a.label("lf_sec").raw(0, 0)
    a.label("lf_dst").raw(0, 0)
    a.label("lf_cnt").raw(0, 0)
    a.label("lf_cb").raw(0, 0)
    a.label("lf_cbb").raw(0, 0)
    code = bytearray(a.bytes())
    dispatch = a.labels["jsys_dispatch"]
    off = a.labels["door_b0"] - 0x0800
    assert code[off] == 0 and code[off + 1] == 0 and code[off + 2] == 0
    assert code[0x7E0:0x800] == bytes(32), "ROM stack shadow 0x0FE0-0x0FFF must stay padding"
    assert 0x0800 + len(code) < 0x2F20, "kernel code must leave stack headroom below the JSYS stack top (0x2F40)"
    code[off] = 0x71  # jmp_abs
    code[off + 1] = (dispatch >> 8) & 0xFF
    code[off + 2] = dispatch & 0xFF
    return bytes(code)

def main():
    focal, _asm = build_focal()
    focal_sectors = -(-len(focal) // 400)
    focal_sector = 0
    for _ in range(6):
        kernel = build_kernel2(focal_sector, focal_sectors)
        generated = {"kernel.bin": kernel, "focal.bin": focal, "egg.bin": build_egg()}
        write_system_members(STAGE, generated)
        members = collect_library_members(STAGE, generated, ["KERNEL"], last=["FOCAL"])
        new_sector = DATA + member_pages(members)["FOCAL"] // 2
        if new_sector == focal_sector:
            break
        focal_sector = new_sector
    else:
        raise RuntimeError("layout did not converge")
    pack_hawk_image(root, members, OUT)
    print(f"FOCAL at sector 0x{focal_sector:04X}+{focal_sectors} -> 0x{FOCAL_LOAD:04X}; wrote {OUT}")

if __name__ == "__main__":
    main()
