# Hawk image layout (Disk6-compatible)

Built by `scripts/mkhawk.py` (test image: `scripts/mk_test_os.py` -> `out/os.img`;
boot it with `HAWK=out/os.img ./scripts/boot_hawk.sh`).

Geometry: 12,992 records, 400-byte logical sectors, 512-byte stride (112 bytes of
`0xFF` padding); `--stride 400` for packed images.  Hawk sector address
`F141/F142` equals the logical sector number (16 sectors/track, 2 heads).

| Sector | Contents |
| --- | --- |
| 0 | Boot sector (stage 1), loaded by the bootstrap ROM at `0x0100`, entry `0x0103` |
| 1-13 | free (room for a larger stage 1.5) |
| `0x0E` | Disk6 control sector: bytes 4-9 = `EF 2C E4 54 FF FF` (flag `FFFF`, volume sector -> `0x10`) |
| `0x10` | Volume header (label, UAL base u24 at offset 13) and catalog, 16-byte entries from offset 16, terminated by `84 8D` |
| `0x12-0x17` | UAL: per-file allocation maps |
| `0x20...` | `SYSTEM` library data |

## Catalog entry (16 bytes)
`name[10]` (upper case, high bit set, padded `A0`), map index, map sector (u16, UAL
relative), attribute, date (0).  Only `SYSTEM` (attr `15`) exists today.

## Allocation map
Header: length-1 (u16), load address (u16), FSI shift (0), class (0); then 3-byte
sector numbers, `FFFFFF` terminator.  When a UAL sector fills, an entry
`(next ^ 0xFFFF) u16, index byte` continues at that index of UAL-relative sector `next`.
Allocation is one sector per extent.  There is **no free-space map yet** (the
original `@SFAL0` format is not decoded).

## SYSTEM library
A library is a catalog file whose data starts with a blank name, then 16-byte
member rows from offset 16 (`84 8D` ends): `name[10]`, byte 10 = start page % 128,
byte 12 = `0x08 + start page // 128`, byte 13 = attr (`14`).  Pages are 200 bytes.
mkhawk starts every member on a sector boundary (even page), so member N is at
sector `0x20 + page/2`.  `basic.system` is `SYSTEM/BASIC`, `command.system` is
`SYSTEM/COMMAND`; the kernel is `SYSTEM/KERNEL`.  Member names are max 10 chars.

## Boot sector
Parameters at `0x0105`: start sector, sector count, load address, entry address
(all u16, patched by mkhawk).  It reads each sector with the same Hawk/DMA sequence
HDIPL uses (DMA count `FE6F`, seek `02`, read `00`, wait on `F144/F145`) and jumps to
the entry.  On error it prints `HAWK READ ERROR` and halts.  Kernel default
load/entry: `0x0800`.

## Verified
biscvit boots `out/os.img` and runs the kernel; tricorn's `hawk-file-sectors.py`
and cordwright (`ls -l /h/SYSTEM`) read the catalog, allocation and members.
Not yet tried: Meisaka emulators, real hardware.
