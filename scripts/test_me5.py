#!/usr/bin/env python3
"""ME-5 sequence probe: replicate the fs_save transfer pattern at level 0.

fill -> write other sectors -> read target back -> write target (flush)
-> verify where the flush landed (0x58 vs 0x50).
"""
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root)); sys.path.insert(0, str(root / "scripts"))
from cpu6asm import Asm
import build_stage2

LOAD = 0x5000
CB = 0x5F00
PA = 0x6000
PB = 0x6400
PT = 0x6800
RB = 0x6C00


def print_msg(a, label):
    a.lda_label(label).xaz().ldbb_i(2).svc(0x40)


def set_cb(a, sector, buf):
    a.lda_i(sector).sta_d(CB)
    a.lda_i(buf).sta_d(CB + 2)


def verdict(a, ok_label, ok_msg, bad_msg):
    a.lda_d("CMPF").ldb_i(1).sab().bz(ok_label)
    print_msg(a, bad_msg)
    a.jmp_abs(ok_label + "_done")
    a.label(ok_label)
    print_msg(a, ok_msg)
    a.label(ok_label + "_done")


def build_probe():
    a = Asm(LOAD)
    a.vars_at(0x5F80)
    a.var("cnt"); a.var("FBUF"); a.var("FPAT"); a.var("CMPB"); a.var("CMPF")
    print_msg(a, "m_start")
    a.lda_i(PA).sta_d("FBUF"); a.lda_i(0x4141).sta_d("FPAT"); a.jsr_abs("fill_sub")
    a.lda_i(PB).sta_d("FBUF"); a.lda_i(0x4242).sta_d("FPAT"); a.jsr_abs("fill_sub")
    a.lda_i(PT).sta_d("FBUF"); a.lda_i(0x4D35).sta_d("FPAT"); a.jsr_abs("fill_sub")
    set_cb(a, 0x58, PA); a.jsr_abs("wr_sub")
    set_cb(a, 0x60, PB); a.jsr_abs("wr_sub")
    set_cb(a, 0x61, PB); a.jsr_abs("wr_sub")
    set_cb(a, 0x58, RB); a.jsr_abs("rd_sub")
    a.lda_i(PA).sta_d("CMPB"); a.jsr_abs("cmp_sub")
    verdict(a, "v_seq1", "m_seq1ok", "m_seq1bad")
    set_cb(a, 0x58, PT); a.jsr_abs("wr_sub")
    set_cb(a, 0x58, RB); a.jsr_abs("rd_sub")
    a.lda_i(PT).sta_d("CMPB"); a.jsr_abs("cmp_sub")
    verdict(a, "v_fl", "m_flok", "m_flbad")
    set_cb(a, 0x50, RB); a.jsr_abs("rd_sub")
    a.lda_i(PT).sta_d("CMPB"); a.jsr_abs("cmp_sub")
    verdict(a, "v_50", "m_at50y", "m_at50n")
    a.label("done")
    a.rsr()
    # ---- subroutines ----
    a.label("fill_sub")
    a.lda_i(0).sta_d("cnt")
    a.lda_d("FBUF").xaz()
    a.label("fill_l")
    a.ldb_d("FPAT").stb_z(0)
    a.xfr("Z", "A").ldb_i(2).aab().xfr("B", "Z")
    a.lda_d("cnt").ldb_i(1).aab().stb_d("cnt")
    a.lda_d("cnt").ldb_i(200).sab()
    a.bnz("fill_l")
    a.rsr()
    a.label("wr_sub")
    a.ldb_i(CB).jsr_abs(0x080F)
    a.ldbb_i(0).sabb().bz("wr_ok")
    a.jmp_abs("xerr")
    a.label("wr_ok")
    a.rsr()
    a.label("rd_sub")
    a.ldb_i(CB).jsr_abs(0x080C)
    a.ldbb_i(0).sabb().bz("rd_ok")
    a.jmp_abs("xerr")
    a.label("rd_ok")
    a.rsr()
    a.label("xerr")
    print_msg(a, "m_err")
    a.jmp_abs("done")
    a.label("cmp_sub")
    a.lda_i(1).sta_d("CMPF")
    a.lda_i(0).sta_d("cnt")
    a.lda_i(RB).xaz()
    a.lda_d("CMPB").xfr("A", "Y")
    a.label("cmp_l")
    a.lda_z(0).ldb_x("Y", disp=0).sab().bz("cmp_eq")
    a.lda_i(0).sta_d("CMPF")
    a.jmp_abs("cmp_done")
    a.label("cmp_eq")
    a.xfr("Z", "A").ldb_i(2).aab().xfr("B", "Z")
    a.xfr("Y", "A").ldb_i(2).aab().xfr("B", "Y")
    a.lda_d("cnt").ldb_i(1).aab().stb_d("cnt")
    a.lda_d("cnt").ldb_i(32).sab()
    a.bnz("cmp_l")
    a.label("cmp_done")
    a.rsr()
    # ---- messages ----
    a.label("m_start").raw(*b"ME5 PROBE\r\n\x00")
    a.label("m_seq1ok").raw(*b"SEQ1 OK\r\n\x00")
    a.label("m_seq1bad").raw(*b"SEQ1 BAD\r\n\x00")
    a.label("m_flok").raw(*b"FLUSH58 OK\r\n\x00")
    a.label("m_flbad").raw(*b"FLUSH58 BAD\r\n\x00")
    a.label("m_at50y").raw(*b"AT50 YES\r\n\x00")
    a.label("m_at50n").raw(*b"AT50 NO\r\n\x00")
    a.label("m_err").raw(*b"XFER ERR\r\n\x00")
    code = a.bytes()
    return b"CV" + LOAD.to_bytes(2, "big") * 2 + len(code).to_bytes(2, "big") + b"\x01" + code


def main():
    build_stage2.build_focal = lambda: (build_probe(), None)
    build_stage2.OUT = root / "out" / "test-me5.img"
    build_stage2.main()


if __name__ == "__main__":
    main()
