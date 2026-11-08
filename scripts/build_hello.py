#!/usr/bin/env python3
"""Generate a small cvit executable that returns to COMMAND."""
from pathlib import Path
from cpu6asm import Asm


def build_hello():
    load = 0x5000
    a = Asm(load)
    a.lda_label("msg").xaz().ldbb_i(2).svc(0x40).rsr()
    a.label("msg").raw(*b"HELLO FROM /SYSTEM/HELLO\r\n\x00")
    code = a.bytes()
    return b"CV" + load.to_bytes(2, "big") * 2 + len(code).to_bytes(2, "big") + b"\x01" + code


if __name__ == "__main__":
    path = Path("out/hello.bin")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_hello())
    print(path)
