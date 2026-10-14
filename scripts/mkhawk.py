#!/usr/bin/env python3
"""Build a bootable Disk6-style Hawk image.  See docs/hawk-layout.md.

  mkhawk.py OUT.img --member KERNEL=kernel.bin [--member BASIC=basic.bin ...]

Members go into the SYSTEM library (so basic.system -> SYSTEM/BASIC).  HELP
members can be supplied with --help-member NAME=FILE.  The first-stage boot
sector (sector 0) loads KERNEL into memory and jumps to it.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cpu6asm import Asm  # noqa: E402

PAYLOAD = 400
SECTORS = 0x32C0
CONTROL, VOLUME, UAL, DATA = 0x0E, 0x10, 0x12, 0x20
UAL_SECTORS = 6
HELP_UAL, HELP_DATA = 0x18, 0x100
PAGE = 200


def hi(s, width=10):
    s = s.upper()
    assert len(s) <= width and all(32 <= ord(c) < 127 for c in s), s
    return bytes((ord(c) | 0x80) for c in s.ljust(width))


def boot_sector(sec, count, dst, entry):
    """Stage 1: read COUNT sectors from SEC to DST over Hawk DMA, jump to ENTRY."""
    a = Asm(0x0100)
    a.raw(0x01, 0x01, 0x01)          # 0100: pad
    a.jmp("start")                   # 0103
    p_sec, p_cnt, p_dst, p_ent = 0x0105, 0x0107, 0x0109, 0x010B
    a.u16(sec).u16(count).u16(dst).u16(entry)
    a.label("start")
    a.label("loop")
    a.lda_d(p_cnt).bz("done")
    a.lda_d(p_dst).dma_sad_a()
    a.lda_i(0xFE6F).dma_sct_a()      # -401 -> 400 bytes
    a.dma_sdv_0().dma_eab()
    a.lda_i(0xF140).xaz()            # Z = Hawk registers
    a.jsr("ready")
    a.lda_d(p_sec).ldb_i(0x3FFF).nab().stb_z(1)   # F141/F142 = sector address
    a.ldab_i(2).stab_z(8)            # seek
    a.jsr("ready")
    a.ldab_i(0).stab_z(8)            # read
    a.jsr("busy")
    a.xfrb_au_al().bnz("error")      # AU = F144 status byte
    a.lda_d(p_sec).ina().sta_d(p_sec)
    a.lda_d(p_dst).ldb_i(PAYLOAD).aab().stb_d(p_dst)
    a.lda_d(p_cnt).ldb_i(0xFFFF).aab().stb_d(p_cnt)
    a.jmp("loop")
    a.label("done")
    a.lda_d(p_ent).xay().jmp_y()
    # same wait sequences HDIPL uses (F04F5 falls into F04FB)
    a.label("busy")
    a.ldab_z(4).srab().bl("busy")
    a.label("ready")
    a.lda_z(4).ldbb_i(0x30).andb_bl_al().sabb().bnz("ready").rsr()
    a.label("error")
    a.print("HAWK READ ERROR\r\n").hlt().jmp("error")
    code = a.bytes()
    assert len(code) <= PAYLOAD, len(code)
    return code


def member_type(name, path):
    return 0x04 if Path(path).suffix.lower() in (".txt", ".text") else 0x14


def build_library(members):
    names = [n for n, _data, _typ in members]
    assert len(names) == len(set(names)), "duplicate member"
    assert len(members) * 16 + 32 <= PAGE, "too many members for one directory page"
    pages, start = {}, 2
    for n, data, _typ in members:
        pages[n] = start
        start += max(2, (-(-len(data) // PAGE) + 1) & ~1)   # whole sectors; even empty files get one sector
    lib = bytearray(start * PAGE)
    lib[0:10] = hi("")
    for i, (n, data, typ) in enumerate(members):
        row = lib[16 + i * 16:32 + i * 16]
        row[0:10] = hi(n)
        row[10] = pages[n] % 128
        row[12] = 0x08 + pages[n] // 128
        row[13] = typ
        lib[16 + i * 16:32 + i * 16] = row
        lib[pages[n] * PAGE:pages[n] * PAGE + len(data)] = data
    end = 16 + len(members) * 16
    lib[end], lib[end + 1] = 0x84, 0x8D
    return lib, pages


def write_ual(sec, ual_sector, data_sector, nsec):
    per = (PAYLOAD - 6) // 3
    sectors = [data_sector + i for i in range(nsec)]
    ual = [bytearray(PAYLOAD) for _ in range(UAL_SECTORS)]
    ual[0][0:2] = (nsec - 1).to_bytes(2, "big")
    ual[0][2:4] = (0).to_bytes(2, "big")         # load address
    ual[0][4] = 0                                # FSI shift 0
    ual[0][5] = 0
    cur, off = 0, 6
    cap = lambda off: (PAYLOAD - off) // 3
    i = 0
    while i < len(sectors):
        room = cap(off) - 1                      # keep one slot for continuation/terminator
        chunk = sectors[i:i + room]
        for s in chunk:
            ual[cur][off:off + 3] = s.to_bytes(3, "big")
            off += 3
        i += len(chunk)
        if i < len(sectors):
            cur += 1
            assert cur < UAL_SECTORS, "image too large for UAL area"
            ual[cur - 1][off:off + 3] = bytes([(cur ^ 0xFFFF) >> 8 & 255, (cur ^ 0xFFFF) & 255, 0])
            off = 0
    ual[cur][off:off + 3] = b"\xff\xff\xff"
    for k, u in enumerate(ual):
        sec(ual_sector + k)[:] = u


def build(system_members, help_members, label, load, entry, stride, boot=True):
    img = bytearray(SECTORS * stride)
    for n in range(SECTORS):
        img[n * stride + PAYLOAD:(n + 1) * stride] = b"\xff" * (stride - PAYLOAD)

    def sec(n):
        return memoryview(img)[n * stride:n * stride + PAYLOAD]

    # --- libraries: page 0 = directory, members on sector boundaries
    system_lib, system_pages = build_library(system_members)
    system_nsec = len(system_lib) // PAYLOAD
    assert DATA + system_nsec <= HELP_DATA, "SYSTEM library overlaps HELP library"
    for i in range(system_nsec):
        sec(DATA + i)[:] = system_lib[i * PAYLOAD:(i + 1) * PAYLOAD]

    help_lib, _help_pages = build_library(help_members)
    help_nsec = len(help_lib) // PAYLOAD
    assert HELP_DATA + help_nsec <= SECTORS
    for i in range(help_nsec):
        sec(HELP_DATA + i)[:] = help_lib[i * PAYLOAD:(i + 1) * PAYLOAD]

    # --- control sector, volume header, root catalog
    sec(CONTROL)[4:10] = bytes([0xEF, 0x2C, 0xE4, 0x54, 0xFF, 0xFF])
    vol = sec(VOLUME)
    vol[0:10] = hi(label)
    vol[13:16] = UAL.to_bytes(3, "big")
    ent = vol[16:32]
    ent[0:10] = hi("SYSTEM")
    ent[10] = 0                                  # map index 0
    ent[11:13] = (0).to_bytes(2, "big")          # UAL-relative map sector 0
    ent[13] = 0x15
    vol[16:32] = ent
    ent = vol[32:48]
    ent[0:10] = hi("HELP")
    ent[10] = 1                                  # map index 1
    ent[11:13] = (HELP_UAL - UAL).to_bytes(2, "big")
    ent[13] = 0x15
    vol[32:48] = ent
    vol[48], vol[49] = 0x84, 0x8D

    # --- allocation maps
    write_ual(sec, UAL, DATA, system_nsec)
    write_ual(sec, HELP_UAL, HELP_DATA, help_nsec)

    # --- boot sector
    if boot:
        member_data = {n: data for n, data, _typ in system_members}
        k = system_pages["KERNEL"]
        assert k % 2 == 0
        boot_code = boot_sector(DATA + k // 2, -(-len(member_data["KERNEL"]) // PAYLOAD), load, entry)
        sec(0)[:len(boot_code)] = boot_code
        return bytes(img), DATA + k // 2
    return bytes(img), None


def parse_member(spec, parser):
    n, _, f = spec.partition("=")
    if not n or not f:
        parser.error(f"bad member spec {spec!r}; expected NAME=FILE")
    return n.upper(), Path(f).read_bytes(), member_type(n, f)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out")
    ap.add_argument("--member", action="append", default=[], metavar="NAME=FILE")
    ap.add_argument("--help-member", action="append", default=[], metavar="NAME=FILE")
    ap.add_argument("--label", default="BISCVIT")
    ap.add_argument("--load", type=lambda x: int(x, 0), default=0x0800)
    ap.add_argument("--entry", type=lambda x: int(x, 0))
    ap.add_argument("--stride", type=int, default=512, choices=(400, 512))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-boot", action="store_true", help="format a non-boot data image; KERNEL is not required")
    a = ap.parse_args()
    system_members = [parse_member(m, ap) for m in a.member]
    help_members = [parse_member(m, ap) for m in a.help_member]
    if not a.no_boot and "KERNEL" not in {n for n, _data, _typ in system_members}:
        ap.error("need --member KERNEL=file")
    out = Path(a.out)
    if out.exists() and not a.force:
        ap.error(f"{out} exists (use --force)")
    img, ksec = build(system_members, help_members, a.label, a.load, a.entry if a.entry is not None else a.load, a.stride, boot=not a.no_boot)
    out.write_bytes(img)
    if ksec is None:
        print(f"wrote {out}: {len(img)} bytes, stride {a.stride}; non-boot data image")
    else:
        print(f"wrote {out}: {len(img)} bytes, stride {a.stride}; KERNEL at sector 0x{ksec:04X} -> 0x{a.load:04X}")


if __name__ == "__main__":
    main()
