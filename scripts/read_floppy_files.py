#!/usr/bin/env python3
"""List/extract files from a Centurion flat 400-byte-sector floppy image.

This implements the Disk-6 directory/UAL logic used by the Meisaka Centurion
emulator's DiskVol viewer.  It is meant for flat sector images where logical
sector N is at offset N * sector_size.

Examples:
  scripts/read_floppy_files.py /tmp/cops-new.img --list
  scripts/read_floppy_files.py /tmp/cops-new.img --cat @LOAD | xxd
  scripts/read_floppy_files.py /tmp/cops-new.img --extract @LOAD /tmp/LOAD.bin
  scripts/read_floppy_files.py /tmp/cops-new.img --extract-all /tmp/cops-files
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SECTOR_SIZE = 400

FILE_TYPES = [
    ('D', 'RAW'), ('B', 'BIN'), ('A', 'TXT'), ('C', 'BIN'),
    ('E', 'BIN'), ('L', 'VOL'), ('I', 'RAW'), ('S', 'RAWS'),
    ('Q', 'RAWQ'), ('X', 'FILE9'), ('X', 'FILE10'), ('X', 'FILE11'),
    ('X', 'FILE12'), ('X', 'FILE13'), ('X', 'FILE14'), (' ', 'FILE15'),
]


@dataclass
class DirEnt:
    name: str
    map_sect: int
    map_index: int
    attr: int
    date: int
    file_type: str
    file_type_long: str
    ual_base: int
    loadaddr: int
    cls: int
    fsi_shift: int
    fsi: int
    length_sectors: int
    ual: list[int]


def u16be(b: bytes | bytearray, off: int) -> int:
    return (b[off] << 8) | b[off + 1]


def u24be(b: bytes | bytearray, off: int) -> int:
    return (b[off] << 16) | (b[off + 1] << 8) | b[off + 2]


def fixed_str(b: bytes | bytearray, off: int, count: int) -> str:
    chars: list[str] = []
    for c in b[off:off + count]:
        c &= 0x7f
        if c == 0:
            break
        if c < 32:
            chars.append(f'^{c:02X}')
        else:
            chars.append(chr(c))
    return ''.join(chars).rstrip()


class Disk6:
    def __init__(self, data: bytes, sector_size: int = SECTOR_SIZE):
        self.data = data
        self.sector_size = sector_size
        self.max_sector = len(data) // sector_size
        self.disk6_flag = 0
        self.sys_date = 0
        self.guard = 0
        self.guarded = False
        self.key = 100
        self.dir_sector = 16
        self.ual_sector = 0
        self.name = ''
        self.status = ''
        self.entries: list[DirEnt] = []

    def read_sector(self, sector: int) -> bytes:
        if sector < 0 or sector >= self.max_sector:
            raise IndexError(f'sector out of range: {sector:#x} >= {self.max_sector:#x}')
        off = sector * self.sector_size
        return self.data[off:off + self.sector_size]

    def decode_volume(self) -> None:
        vrec = self.read_sector(14)
        self.sys_date = u16be(vrec, 0)
        self.guard = u16be(vrec, 2)
        self.guarded = self.guard != 0x4321
        self.disk6_flag = u16be(vrec, 8)
        self.dir_sector = 16

        if self.disk6_flag == 0xffff:
            disk_key = u16be(vrec, 6)
            disk_key ^= 0xffff
            disk_key = ((disk_key >> 1) | (disk_key << 15)) & 0xffff
            disk_key ^= 0x8db1
            self.key = disk_key

            dvo = vrec[5]
            disk_vol_pre = ((vrec[4] ^ dvo) << 8) | dvo
            disk_vol_pre ^= 0x3cb1
            self.dir_sector = ((disk_vol_pre + disk_key) & 0xfff) << 4
        elif self.disk6_flag == 0xfdfd:
            self.status = 'INIT'
        elif self.disk6_flag != 0:
            self.status = f'unknown disk flag {self.disk6_flag:04X}'

        if self.dir_sector >= self.max_sector:
            self.status = f'directory sector out of range: {self.dir_sector:#x}'
            return

        dsec = self.read_sector(self.dir_sector)
        self.ual_sector = u24be(dsec, 13)
        if self.ual_sector == 0:
            # Meisaka labels this NUL, but still allow parsing; some recovered
            # boot/catalog sectors are incomplete and useful anyway.
            self.status = self.status or 'NUL/zero UAL base'
        elif self.ual_sector >= self.max_sector:
            self.status = f'UAL base out of range: {self.ual_sector:#x}'
        else:
            self.name = fixed_str(dsec, 0, 10)

    def read_ual_sectors(self, ent: DirEnt) -> list[int]:
        sectors: list[int] = []
        buf = self.read_sector(ent.ual_base)
        ofs = ent.map_index + 6
        limit = 0
        while limit < 100 and len(sectors) < ent.length_sectors:
            limit += 1
            if ofs + 3 > self.sector_size:
                break
            si = u24be(buf, ofs)
            if si == 0xffffff:
                break
            if si > 0x800000:
                # Continuation pointer: u16 next_ual_sector ^ 0xffff,
                # u8 index/3 in the next UAL sector.
                next_ual = u16be(buf, ofs) ^ 0xffff
                ofs = buf[ofs + 2] * 3
                buf = self.read_sector(next_ual + self.ual_sector)
            else:
                sectors.append(si)
                ofs += 3
        return sectors

    def parse_dir_entry(self, dsec: bytes, off: int) -> DirEnt | None:
        name = fixed_str(dsec, off, 10)
        if not name:
            return None
        map_index = dsec[off + 10] * 3
        map_sect = u16be(dsec, off + 11)
        attr = dsec[off + 13]
        date = u16be(dsec, off + 14)
        ft, ft_long = FILE_TYPES[attr & 0x0f]
        ual_base = self.ual_sector + map_sect
        if ual_base >= self.max_sector or map_index >= self.sector_size - 4:
            return None
        ual = self.read_sector(ual_base)
        length = u16be(ual, map_index) + 1
        loadaddr = u16be(ual, map_index + 2)
        fsi_shift = ual[map_index + 4]
        cls = ual[map_index + 5]
        if fsi_shift > 15:
            return None
        ent = DirEnt(
            name=name, map_sect=map_sect, map_index=map_index, attr=attr,
            date=date, file_type=ft, file_type_long=ft_long, ual_base=ual_base,
            loadaddr=loadaddr, cls=cls, fsi_shift=fsi_shift, fsi=1 << fsi_shift,
            length_sectors=length, ual=[],
        )
        try:
            ent.ual = self.read_ual_sectors(ent)
        except IndexError:
            return None
        return ent

    def scan_dir(self) -> list[DirEnt]:
        self.decode_volume()
        self.entries = []
        if self.dir_sector >= self.max_sector:
            return self.entries

        sector = self.dir_sector
        entry = 16
        ent_itr = 0
        bad_itr = 0
        dsec = self.read_sector(sector)
        while sector < self.max_sector and ent_itr <= 800 and bad_itr <= 10:
            while entry < self.sector_size:
                ent_itr += 1
                if ent_itr > 800:
                    return self.entries
                if dsec[entry] == 0x84 and entry + 1 < self.sector_size and dsec[entry + 1] == 0x8d:
                    return self.entries
                if dsec[entry] != 0:
                    ent = self.parse_dir_entry(dsec, entry)
                    if ent is not None:
                        self.entries.append(ent)
                    else:
                        bad_itr += 1
                entry += 16
            sector += 1
            entry = 0
            if sector < self.max_sector:
                dsec = self.read_sector(sector)
        return self.entries

    def read_file(self, ent: DirEnt) -> bytes:
        out = bytearray()
        remaining = ent.length_sectors
        for start in ent.ual:
            for sec in range(start, start + ent.fsi):
                if remaining <= 0:
                    break
                # UAL file-sector entries are absolute Disk-6 sector numbers.
                # FDIPL's @LOAD walk reads entries such as $02C4 directly, not
                # relative to the UAL base sector ($0020).
                out.extend(self.read_sector(sec))
                remaining -= 1
            if remaining <= 0:
                break
        return bytes(out)

    def find(self, name: str) -> DirEnt | None:
        want = name.upper().rstrip()
        for ent in self.entries:
            if ent.name.upper().rstrip() == want:
                return ent
        return None


def safe_name(name: str) -> str:
    s = ''.join(chr(c & 0x7f) for c in name.encode('ascii', 'replace'))
    s = re.sub(r'[^A-Za-z0-9_.@+-]+', '_', s.strip())
    return s or 'unnamed'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('image', type=Path)
    ap.add_argument('--sector-size', type=int, default=SECTOR_SIZE)
    ap.add_argument('--list', action='store_true', help='list directory entries')
    ap.add_argument('--cat', metavar='NAME', help='write file contents to stdout')
    ap.add_argument('--extract', nargs=2, metavar=('NAME', 'OUT'), help='extract one file')
    ap.add_argument('--extract-all', metavar='DIR', help='extract all files')
    args = ap.parse_args()

    disk = Disk6(args.image.read_bytes(), args.sector_size)
    entries = disk.scan_dir()

    if args.list or (not args.cat and not args.extract and not args.extract_all):
        print(f'image: {args.image}')
        print(f'sectors: {disk.max_sector}  sector_size: {disk.sector_size}')
        print(f'disk6_flag: {disk.disk6_flag:04X}  key/code: {disk.key}  dir_sector: {disk.dir_sector:04X}  ual_base: {disk.ual_sector:04X}  status: {disk.status}')
        for ent in entries:
            print(f'{ent.name:<10} {ent.file_type} len={ent.length_sectors:04X}s fsi={ent.fsi:<3} load={ent.loadaddr:04X} cls={ent.cls:02X} map=<{ent.map_sect:04X}:{ent.map_index:03X}> ual={",".join(f"{s:04X}" for s in ent.ual[:8])}{"..." if len(ent.ual) > 8 else ""}')

    if args.cat:
        ent = disk.find(args.cat)
        if ent is None:
            raise SystemExit(f'file not found: {args.cat}')
        sys.stdout.buffer.write(disk.read_file(ent))

    if args.extract:
        name, out = args.extract
        ent = disk.find(name)
        if ent is None:
            raise SystemExit(f'file not found: {name}')
        Path(out).write_bytes(disk.read_file(ent))
        print(f'wrote {out}: {ent.name} ({ent.length_sectors} sectors)')

    if args.extract_all:
        outdir = Path(args.extract_all)
        outdir.mkdir(parents=True, exist_ok=True)
        for ent in entries:
            out = outdir / safe_name(ent.name)
            out.write_bytes(disk.read_file(ent))
            print(f'wrote {out}: {ent.length_sectors} sectors')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
