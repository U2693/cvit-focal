#!/usr/bin/env python3
"""Create out/data.img as a formatted, non-boot cvit Hawk work platter.

The image is intended for H1: and contains a writable /SYSTEM library with
mailbox files for host/guest collaboration.  Files are preallocated by filling
with spaces; cvit trims trailing spaces on read but keeps the capacity for CED
and host-side writes.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mkhawk import build  # noqa: E402

TXT = 0x04
PAYLOAD = 400
STRIDE = 512


def blank_text(capacity):
    return b" " * capacity


def main():
    out = ROOT / "out/data.img"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Keep frequently-edited mailbox files first and generously preallocated.
    # Capacity visible to CvitFileSystem is the gap to the next directory row's
    # start page, rounded by mkhawk to whole sectors.
    members = [
        ("REQUEST", blank_text(8 * PAYLOAD), TXT),
        ("RESPONSE", blank_text(16 * PAYLOAD), TXT),
        ("STATUS", b"ID: 000000\r\nSTATE: EMPTY\r\n", TXT),
        ("LOG", blank_text(16 * PAYLOAD), TXT),
        ("SCRATCH", blank_text(16 * PAYLOAD), TXT),
        ("README", (
            b"CVIT H1: DATA PLATTER\r\n"
            b"REQUEST/STATUS/RESPONSE are mailbox files for host AI tools.\r\n"
            b"Use H0: for the boot/system image and H1: for disposable work.\r\n"
        ), TXT),
    ]

    img, _ = build(members, [], "DATA", 0x0800, 0x0800, STRIDE, boot=False)
    out.write_bytes(img)
    print(f"wrote {out}: {len(img)} bytes, stride {STRIDE}; formatted non-boot cvit data image")
    print("SYSTEM members:", ", ".join(n for n, _data, _typ in members))


if __name__ == "__main__":
    main()
