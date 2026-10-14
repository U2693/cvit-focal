#!/usr/bin/env python3
"""Export a cvit/Disk6 Hawk platter to a Windows-friendly directory tree.

By default this creates a temporary directory and prints its path:

    scripts/hawk_export_tmp.py out/data.img

Or export to a chosen directory:

    scripts/hawk_export_tmp.py out/data.img /tmp/data-export

The output uses normal files and directories, with .TXT/.SYS/.BIN extensions and
CRLF-normalized text, suitable for copying to Windows or packaging with any ISO
creator.
"""
from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from pathlib import Path

PAYLOAD = 400
DEFAULT_STRIDE = 512
CONTROL = 0x0E
VOLUME = 0x10
DEFAULT_UAL = 0x12
PAGE = 200
ROOT_FIRST_ROW = 16
ROW = 16
NAME_LEN = 10

TYPE_EXT = {
    0x04: ".TXT",
    0x14: ".SYS",
    0x15: "",
}

TYPE_NAME = {
    0x04: "TXT",
    0x14: "SYS",
    0x15: "LIB",
}


def detect_stride(image: bytes) -> int:
    """Pick 512 if the Disk6 control sector is present there, else packed 400."""
    for stride in (512, 400):
        off = CONTROL * stride
        if off + 10 <= len(image) and image[off + 4:off + 10] == bytes([0xEF, 0x2C, 0xE4, 0x54, 0xFF, 0xFF]):
            return stride
    return DEFAULT_STRIDE


class HawkImage:
    def __init__(self, image: bytes, stride: int):
        self.image = image
        self.stride = stride
        self.sector_count = len(image) // stride

    def sector(self, n: int) -> bytes:
        off = n * self.stride
        if n < 0 or off + PAYLOAD > len(self.image):
            return b""
        return self.image[off:off + PAYLOAD]

    def sectors_bytes(self, sectors: list[int]) -> bytes:
        return b"".join(self.sector(s) for s in sectors)


def decode_name(data: bytes) -> str:
    s = "".join(chr(b & 0x7F) for b in data[:NAME_LEN]).rstrip()
    return s or "UNTITLED"


def safe_name(name: str) -> str:
    name = name.upper().strip()
    name = re.sub(r"[^A-Z0-9._$~-]+", "_", name)
    name = name.strip(". ")
    return name or "UNTITLED"


def u16(b: bytes, off: int) -> int:
    return (b[off] << 8) | b[off + 1]


def parse_rows(data: bytes, limit: int = PAYLOAD):
    for off in range(ROOT_FIRST_ROW, min(limit, len(data) - ROW + 1), ROW):
        if data[off] == 0x84 and data[off + 1] == 0x8D:
            break
        if data[off] in (0x00, 0xFF):
            continue
        name = decode_name(data[off:off + NAME_LEN])
        page = data[off + 10] + max(0, data[off + 12] - 0x08) * 128
        typ = data[off + 13]
        map_index = data[off + 10]
        map_sector = u16(data, off + 11)
        yield {
            "name": name,
            "page": page,
            "type": typ,
            "map_index": map_index,
            "map_sector": map_sector,
        }


def read_ual_sectors(hawk: HawkImage, ual_sector: int, index: int) -> list[int]:
    """Read a mkhawk-style allocation map entry and return logical sectors."""
    ual = hawk.sector(ual_sector)
    if len(ual) < index + 6:
        return []
    length = u16(ual, index) + 1
    sectors: list[int] = []
    cur_ual = ual_sector
    off = index + 6
    guard = 0
    while len(sectors) < length and guard < 64:
        guard += 1
        u = hawk.sector(cur_ual)
        while off + 2 < PAYLOAD and len(sectors) < length:
            a, b, c = u[off], u[off + 1], u[off + 2]
            off += 3
            if a == 0xFF and b == 0xFF and c == 0xFF:
                return sectors
            # mkhawk continuation: (next_ual_relative ^ 0xffff) u16, index byte.
            val16 = (a << 8) | b
            if val16 >= 0x8000 and not (a == 0xFF and b == 0xFF):
                rel = (~val16) & 0xFFFF
                cur_ual = ual_sector + rel
                off = c
                break
            sectors.append((a << 16) | (b << 8) | c)
        else:
            break
    return sectors


def looks_like_library(data: bytes) -> bool:
    return len(data) >= PAGE and all((b & 0x7F) == 0x20 for b in data[:NAME_LEN])


def read_root_libraries(hawk: HawkImage):
    vol = hawk.sector(VOLUME)
    if not vol:
        return "", []
    label = decode_name(vol[:NAME_LEN])
    ual_base = int.from_bytes(vol[13:16], "big") if len(vol) >= 16 else DEFAULT_UAL
    libs = []
    for ent in parse_rows(vol):
        typ = ent["type"]
        if typ != 0x15:
            continue
        ual_sector = ual_base + ent["map_sector"]
        index = ent["map_index"] * 3
        sectors = read_ual_sectors(hawk, ual_sector, index)
        data = hawk.sectors_bytes(sectors)
        # Some current images put each library's map at offset 0 even if the
        # root row's map index is nonzero. Fall back to offset 0 when needed or
        # when the selected sectors do not look like a library directory page.
        if not sectors or not looks_like_library(data):
            sectors = read_ual_sectors(hawk, ual_sector, 0)
            data = hawk.sectors_bytes(sectors)
        libs.append((ent["name"], data))
    return label, libs


def trim_member(data: bytes, typ: int) -> bytes:
    end = len(data)
    if typ == 0x14 and len(data) >= 8 and data[:2] == b"CV":
        declared = 9 + ((data[6] << 8) | data[7])
        if declared <= len(data):
            end = declared
    else:
        while end > 0 and data[end - 1] in (0x00, 0x20, 0x7F):
            end -= 1
    return data[:end]


def text_to_crlf(data: bytes) -> bytes:
    text = data.decode("ascii", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\n", "\r\n").encode("ascii", errors="replace")


def export_library(lib_name: str, lib_data: bytes, out_root: Path):
    out_dir = out_root / safe_name(lib_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = list(parse_rows(lib_data, limit=PAGE))
    pages = sorted((e["page"], e) for e in entries)
    for i, (page, ent) in enumerate(pages):
        next_page = pages[i + 1][0] if i + 1 < len(pages) else len(lib_data) // PAGE
        if next_page <= page:
            next_page = page + 2
        raw = lib_data[page * PAGE:min(len(lib_data), next_page * PAGE)]
        typ = ent["type"]
        data = trim_member(raw, typ)
        ext = TYPE_EXT.get(typ, ".BIN") or ".LIB"
        if typ == 0x04:
            data = text_to_crlf(data)
        path = out_dir / (safe_name(ent["name"]) + ext)
        path.write_bytes(data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", nargs="?", default="out/data.img", help="Hawk image to export, default out/data.img")
    ap.add_argument("outdir", nargs="?", help="output directory; default is a new temp directory")
    ap.add_argument("--force", action="store_true", help="replace output directory if it already exists")
    args = ap.parse_args()

    image_path = Path(args.image)
    image = image_path.read_bytes()
    hawk = HawkImage(image, detect_stride(image))

    if args.outdir:
        out_root = Path(args.outdir)
        if out_root.exists():
            if not args.force:
                ap.error(f"{out_root} exists; use --force")
            shutil.rmtree(out_root)
        out_root.mkdir(parents=True)
    else:
        out_root = Path(tempfile.mkdtemp(prefix="cvit-hawk-"))

    label, libraries = read_root_libraries(hawk)
    for name, data in libraries:
        export_library(name, data, out_root)

    info = out_root / "_CVIT_VOLUME.TXT"
    info.write_text(
        f"Source image: {image_path}\r\n"
        f"Volume label: {label}\r\n"
        f"Sector stride: {hawk.stride}\r\n"
        f"Libraries: {', '.join(name for name, _ in libraries)}\r\n",
        encoding="ascii",
        newline="",
    )

    print(out_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
