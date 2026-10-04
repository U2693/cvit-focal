#!/usr/bin/env python3
"""Build the cvit guest files and pack out/os.img."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "scripts"))

from cvit.constants import COMMAND_LOAD, DATA
from cvit.image import collect_members, member_pages, pack_hawk_image, write_system_members
from cvit.members import generated_members
from cvit.src.command import build_command
from cvit.src.kernel import build_kernel

OS_ROOT = root / "os"
SYSTEM_ROOT = OS_ROOT / "SYSTEM"
HELP_ROOT = OS_ROOT / "HELP"


def build_guest_members():
    """Build guest member payloads whose embedded sector literals depend on layout."""
    # Multi-pass the literals that depend on SYSTEM member placement. Instruction
    # widths are fixed, so later passes preserve the computed layout. All files in
    # ./os/SYSTEM are included as SYSTEM members; generated files override their
    # on-disk contents for this build. ./os/HELP is reserved for the next library
    # once cvit grows multi-library image generation.
    command = build_command(0)
    command_sectors = -(-len(command) // 400)
    kernel = build_kernel(0, command_sectors)
    welcome_sector = command_sector = 0
    for _ in range(6):
        generated = generated_members(kernel, command)
        members = collect_members(SYSTEM_ROOT, generated)
        pages = member_pages(members)
        new_welcome_sector = DATA + pages["WELCOME"] // 2
        new_command_sector = DATA + pages["COMMAND"] // 2
        new_command = build_command(new_welcome_sector)
        new_command_sectors = -(-len(new_command) // 400)
        new_kernel = build_kernel(new_command_sector, new_command_sectors)
        if (new_welcome_sector == welcome_sector and new_command_sector == command_sector and
                new_command == command and new_kernel == kernel and new_command_sectors == command_sectors):
            return generated, welcome_sector, command_sector, command_sectors
        welcome_sector, command_sector = new_welcome_sector, new_command_sector
        command, kernel, command_sectors = new_command, new_kernel, new_command_sectors
    raise RuntimeError("layout did not converge")


def build_image():
    SYSTEM_ROOT.mkdir(parents=True, exist_ok=True)
    HELP_ROOT.mkdir(parents=True, exist_ok=True)

    generated, welcome_sector, command_sector, command_sectors = build_guest_members()
    write_system_members(SYSTEM_ROOT, generated)
    members = collect_members(SYSTEM_ROOT, generated)
    pack_hawk_image(root, members, root / "out/os.img")
    return members, welcome_sector, command_sector, command_sectors


def main():
    members, welcome_sector, command_sector, command_sectors = build_image()
    print("SYSTEM members:", ", ".join(n for n, _p, _data in members))
    print(f"WELCOME at sector 0x{welcome_sector:04X}; COMMAND at sector 0x{command_sector:04X}+{command_sectors} -> 0x{COMMAND_LOAD:04X}")


if __name__ == "__main__":
    main()
