#!/usr/bin/env python3
"""Generate placeholder KERNEL/BASIC/COMMAND files in os/ and build out/os.img."""
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from cpu6asm import Asm

root = Path(__file__).parent.parent
(root / "os").mkdir(exist_ok=True)
a = Asm(0x0800)
a.label("h").print("KERNEL OK\r\n").hlt().jmp("h")
(root / "os/kernel.bin").write_bytes(a.bytes())
(root / "os/basic.bin").write_bytes(b"BASIC placeholder\r" * 20)
(root / "os/command.bin").write_bytes(b"COMMAND placeholder\r" * 30)
(root / "out").mkdir(exist_ok=True)
subprocess.check_call([sys.executable, str(root / "scripts/mkhawk.py"), str(root / "out/os.img"), "--force",
    "--member", f"KERNEL={root}/os/kernel.bin", "--member", f"BASIC={root}/os/basic.bin",
    "--member", f"COMMAND={root}/os/command.bin"])
