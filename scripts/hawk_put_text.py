#!/usr/bin/env python3
"""Put a host text file into a cvit Hawk image member.

Usage:
  scripts/hawk_put_text.py out/data.img /SYSTEM/TWINKLE twinkle.focal
  scripts/hawk_put_text.py out/data.img TWINKLE twinkle.focal

Currently targets mkhawk/cvit-style libraries (/SYSTEM or /HELP) and writes TXT
members, creating the member at the end of the library if needed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

PAYLOAD = 400
PAGE = 200
CONTROL = 0x0E
SYSTEM_DATA = 0x20
SYSTEM_UAL = 0x12
HELP_DATA = 0x100
HELP_UAL = 0x18
DIR_FIRST = 16
ROW = 16
NAME_LEN = 10
TXT = 0x04


def detect_stride(img: bytes) -> int:
    for stride in (512, 400):
        off = CONTROL * stride
        if off + 10 <= len(img) and img[off + 4:off + 10] == bytes([0xEF, 0x2C, 0xE4, 0x54, 0xFF, 0xFF]):
            return stride
    return 512


def sec_off(stride: int, n: int) -> int:
    return n * stride


def decode_name(b: bytes) -> str:
    return "".join(chr(x & 0x7F) for x in b[:NAME_LEN]).rstrip()


def encode_name(name: str) -> bytes:
    name = name.upper()
    if not (1 <= len(name) <= NAME_LEN):
        raise ValueError("member names must be 1..10 chars")
    return bytes(((ord(name[i]) if i < len(name) else 0x20) | 0x80) for i in range(NAME_LEN))


def parse_target(s: str):
    s = s.strip().upper()
    if s.startswith("H0:") or s.startswith("H1:"):
        s = s[3:]
    if not s.startswith("/"):
        return "/SYSTEM", s
    parts = [p for p in s.split("/") if p]
    if len(parts) == 1:
        return "/SYSTEM", parts[0]
    return "/" + parts[0], parts[-1]


def lib_location(prefix: str):
    if prefix == "/SYSTEM" or prefix == "/":
        return SYSTEM_DATA, SYSTEM_UAL
    if prefix == "/HELP":
        return HELP_DATA, HELP_UAL
    raise ValueError("only /SYSTEM and /HELP libraries are supported")


def u16(img: bytearray, off: int) -> int:
    return (img[off] << 8) | img[off + 1]


def write_u16(img: bytearray, off: int, v: int):
    img[off] = (v >> 8) & 0xFF
    img[off + 1] = v & 0xFF


def dir_entries(img: bytearray, stride: int, data_sector: int):
    base = sec_off(stride, data_sector)
    for row in range(DIR_FIRST, PAGE, ROW):
        off = base + row
        if img[off] == 0x84 and img[off + 1] == 0x8D:
            return
        yield off, decode_name(img[off:off + NAME_LEN]), img[off + 10] + max(0, img[off + 12] - 0x08) * 128, img[off + 13]


def find_terminator(img: bytearray, stride: int, data_sector: int) -> int:
    base = sec_off(stride, data_sector)
    for row in range(DIR_FIRST, PAGE, ROW):
        off = base + row
        if img[off] == 0x84 and img[off + 1] == 0x8D:
            return off
    raise ValueError("library directory has no room/terminator")


def member_capacity(img: bytearray, stride: int, data_sector: int, ual_sector: int, page: int) -> int:
    ual = sec_off(stride, ual_sector)
    library_pages = (u16(img, ual) + 1) * 2
    next_page = library_pages
    for _off, _name, p, _typ in dir_entries(img, stride, data_sector):
        if page < p < next_page:
            next_page = p
    return max(0, (next_page - page) * PAGE)


def write_row(img: bytearray, off: int, name: str, page: int, typ: int = TXT):
    img[off:off + NAME_LEN] = encode_name(name)
    img[off + 10] = page % 128
    img[off + 11] = 0
    img[off + 12] = 0x08 + page // 128
    img[off + 13] = typ
    img[off + 14] = 0
    img[off + 15] = 0


def append_ual_sector(img: bytearray, stride: int, ual_sector: int, sector: int):
    for us in range(6):
        off = sec_off(stride, ual_sector + us)
        start = 6 if us == 0 else 0
        for p in range(start, PAYLOAD - 2, 3):
            if img[off + p:off + p + 3] == b"\xff\xff\xff":
                img[off + p:off + p + 3] = sector.to_bytes(3, "big")
                if p + 5 < PAYLOAD:
                    img[off + p + 3:off + p + 6] = b"\xff\xff\xff"
                return
    raise ValueError("UAL is full")


def alloc_sectors(data_len: int) -> int:
    pages = max(2, (((data_len + PAGE - 1) // PAGE + 1) & ~1))
    return pages // 2


def put_text(image_path: Path, target: str, source_path: Path):
    img = bytearray(image_path.read_bytes())
    stride = detect_stride(img)
    prefix, name = parse_target(target)
    data_sector, ual_sector = lib_location(prefix)
    name = name.upper()
    if not (1 <= len(name) <= NAME_LEN):
        raise ValueError("member names must be 1..10 chars")

    data = source_path.read_bytes().replace(b"\r\n", b"\r").replace(b"\n", b"\r")

    found = None
    for off, ent_name, page, typ in dir_entries(img, stride, data_sector):
        if ent_name.upper() == name:
            found = (off, page)
            break

    if found:
        _off, page = found
        cap = member_capacity(img, stride, data_sector, ual_sector, page)
        if len(data) > cap:
            raise ValueError(f"{name} exists but is too small ({cap} bytes capacity, need {len(data)})")
    else:
        ual = sec_off(stride, ual_sector)
        old_nsec = u16(img, ual) + 1
        need_nsec = alloc_sectors(len(data))
        page = old_nsec * 2
        term = find_terminator(img, stride, data_sector)
        if term + ROW + 1 >= sec_off(stride, data_sector) + PAGE:
            raise ValueError("library directory is full")
        write_row(img, term, name, page, TXT)
        img[term + ROW] = 0x84
        img[term + ROW + 1] = 0x8D
        write_u16(img, ual, old_nsec + need_nsec - 1)
        for i in range(need_nsec):
            append_ual_sector(img, stride, ual_sector, data_sector + old_nsec + i)

    cap = member_capacity(img, stride, data_sector, ual_sector, page)
    start_sector = data_sector + page // 2
    start = sec_off(stride, start_sector) + (page & 1) * PAGE
    img[start:start + cap] = b" " * cap
    img[start:start + len(data)] = data
    image_path.write_bytes(img)
    print(f"wrote {image_path}:{prefix}/{name} ({len(data)} bytes, capacity {cap})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image")
    ap.add_argument("target")
    ap.add_argument("source")
    args = ap.parse_args()
    put_text(Path(args.image), args.target, Path(args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
