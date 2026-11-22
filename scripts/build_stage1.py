#!/usr/bin/env python3
"""Stage 1 standalone-FOCAL bring-up: Hawk IPL -> kernel -> DEMO (no COMMAND).
Builds out/stage1.img with only SYSTEM/KERNEL and SYSTEM/DEMO. The stock cvit
kernel loader is pointed at DEMO, loaded at COMMAND_LOAD (0x3000) and jumped
to - the slot FOCAL will take. DEMO prints a banner and exits via the kernel
quit vector (0x0809), which prints BYE and halts."""
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root)); sys.path.insert(0, str(root / "scripts"))
from cpu6asm import Asm
from cvit.constants import COMMAND_LOAD, DATA
from cvit.image import collect_library_members, member_pages, pack_hawk_image, write_system_members
from cvit.src.kernel import build_kernel
QUIT_VECTOR = 0x0809
STAGE = root / "out" / "stage1-system"
OUT = root / "out" / "stage1.img"

def build_demo():
    a = Asm(COMMAND_LOAD)
    a.print("\r\nSTAGE 1 DEMO\r\n")
    a.print("HAWK IPL -> KERNEL -> DEMO\r\n")
    a.print("FOCAL GOES HERE NEXT\r\n")
    a.jmp_abs(QUIT_VECTOR)
    return a.bytes()

def main():
    demo = build_demo()
    demo_sectors = -(-len(demo) // 400)
    demo_sector = 0
    for _ in range(6):
        kernel = build_kernel(demo_sector, demo_sectors)
        generated = {"kernel.bin": kernel, "demo.bin": demo}
        write_system_members(STAGE, generated)
        members = collect_library_members(STAGE, generated, ["KERNEL"], last=["DEMO"])
        new_sector = DATA + member_pages(members)["DEMO"] // 2
        if new_sector == demo_sector:
            break
        demo_sector = new_sector
    else:
        raise RuntimeError("layout did not converge")
    pack_hawk_image(root, members, OUT)
    print(f"DEMO at sector 0x{demo_sector:04X}+{demo_sectors} -> 0x{COMMAND_LOAD:04X}; wrote {OUT}")

if __name__ == "__main__":
    main()
