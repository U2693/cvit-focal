#!/usr/bin/env python3
"""ME-2 probe: kernel write_block/read_block round-trip in the stage-2 system.

Builds out/test-me2.img with the probe in the FOCAL slot. The probe fills a
400-byte buffer with word i = i, writes it to scratch sector 6000 through
the kernel write_block vector (0x080F), zeroes the buffer, reads it back
through read_block (0x080C), and compares word by word. Prints go through
SVC 0x40 fn2, so the same image runs in normal and --bare-metal modes.
"""
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root)); sys.path.insert(0, str(root / "scripts"))
from cpu6asm import Asm
import build_stage2

LOAD = 0x5000
CB = 0x5F00
BUF = 0x6000
SECTOR = 6000


def advance_z(a):
    # Z += 2 (A and B are scratch here)
    a.xfr("Z", "A").ldb_i(2).aab().xfr("B", "Z")


def bump_cnt(a):
    a.lda_d("cnt").ldb_i(1).aab().stb_d("cnt")
    a.lda_d("cnt").ldb_i(200).sab()


def print_msg(a, label):
    a.lda_label(label).xaz().ldbb_i(2).svc(0x40)


def build_probe():
    a = Asm(LOAD)
    a.vars_at(0x5F80)
    a.var("cnt")
    print_msg(a, "m_start")
    a.lda_i(SECTOR).sta_d(CB)
    a.lda_i(BUF).sta_d(CB + 2)
    # fill buf word i = i
    a.lda_i(0).sta_d("cnt")
    a.lda_i(BUF).xaz()
    a.label("fill")
    a.ldb_d("cnt").stb_z(0)
    advance_z(a)
    bump_cnt(a)
    a.bnz("fill")
    # write the sector
    a.ldb_i(CB).jsr_abs(0x080F)
    a.ldbb_i(0).sabb().bnz("werr")
    # zero the buffer
    a.lda_i(0).sta_d("cnt")
    a.lda_i(BUF).xaz()
    a.label("zero")
    a.ldb_i(0).stb_z(0)
    advance_z(a)
    bump_cnt(a)
    a.bnz("zero")
    # read it back
    a.ldb_i(CB).jsr_abs(0x080C)
    a.ldbb_i(0).sabb().bnz("rerr")
    # verify word by word
    a.lda_i(0).sta_d("cnt")
    a.lda_i(BUF).xaz()
    a.label("ver")
    a.lda_z(0).ldb_d("cnt").sab().bnz("bad")
    advance_z(a)
    bump_cnt(a)
    a.bnz("ver")
    print_msg(a, "m_ok")
    a.rsr()
    a.label("werr")
    print_msg(a, "m_werr")
    a.rsr()
    a.label("rerr")
    print_msg(a, "m_rerr")
    a.rsr()
    a.label("bad")
    print_msg(a, "m_bad")
    a.rsr()
    a.label("m_start").raw(*b"ME2 PROBE\r\n\x00")
    a.label("m_ok").raw(*b"WRITE READBACK OK\r\n\x00")
    a.label("m_werr").raw(*b"WRITE STATUS ERROR\r\n\x00")
    a.label("m_rerr").raw(*b"READ STATUS ERROR\r\n\x00")
    a.label("m_bad").raw(*b"READBACK MISMATCH\r\n\x00")
    code = a.bytes()
    return b"CV" + LOAD.to_bytes(2, "big") * 2 + len(code).to_bytes(2, "big") + b"\x01" + code


def main():
    build_stage2.build_focal = lambda: (build_probe(), None)
    build_stage2.OUT = root / "out" / "test-me2.img"
    build_stage2.main()


if __name__ == "__main__":
    main()
