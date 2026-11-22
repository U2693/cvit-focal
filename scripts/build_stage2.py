#!/usr/bin/env python3
"""Stage 2 standalone FOCAL: Hawk IPL -> kernel -> FOCAL (no COMMAND).
Builds out/stage2.img with SYSTEM/KERNEL (stage-2 variant) and SYSTEM/FOCAL.
The variant kernel keeps the stock jump table, syscall stub and read_block,
but its cold start loads the FOCAL member at 0x5000 and JSRs to it; FOCAL
QUIT (RSR) returns into the kernel quit vector: BYE and halt. The member
blob is a 9-byte CV header + code; sectors are loaded to 0x5000-9 so the
code lands exactly at 0x5000. FOCAL console I/O is SVC 0x40 fn 1/2/3,
host-served in biscvit (kernel syscall is the fallthrough for other fns)."""
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root)); sys.path.insert(0, str(root / "scripts"))
from cpu6asm import Asm
from cvit.constants import DATA
from cvit.image import collect_library_members, member_pages, pack_hawk_image, write_system_members
from cvit.src.disk6 import emit_disk6_read_block
from cvit.src.hawk import emit_hawk_read, emit_hawk_waits
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
    a = Asm(0x0800)
    for v in ["cold_start", "warm_start", "syscall", "quit", "read_block", "write_block", "open", "close", "read", "write", "get_file_info", "set_file_info", "create", "destroy", "rename", "set_prefix", "get_prefix"]:
        a.jmp_abs(v)
    a.label("cold_start")
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
    a.label("load_focal")
    for i in range(focal_sectors):
        a.jsr_abs(f"lf_{i}")
    a.rsr()
    for i in range(focal_sectors):
        emit_hawk_read(a, f"lf_{i}", focal_sector + i, FOCAL_LOAD - HDR + 400 * i)
    emit_hawk_waits(a)
    emit_disk6_read_block(a)
    for v in ["write_block", "open", "close", "read", "write", "get_file_info", "set_file_info", "create", "destroy", "rename", "set_prefix", "get_prefix"]:
        a.label(v).print("\r\n?UNIMPL\r\n").rsr()
    return a.bytes()

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
