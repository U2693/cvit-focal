#!/usr/bin/env python3
"""Stage 3 FP differential tests: cpu6_float vs an exact Fraction model.
Run under nix develop: python3 scripts/test_fp_stage3.py"""
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cpu6asm import Asm
from cpu6_float import declare_float_workspace, emit_float_routines

ROOT = Path(__file__).resolve().parent.parent
RES = 0x7000


def enc(sign, m, e):
    if m == 0:
        return 0
    return ((0x80 if sign else 0) | (e + 64)) << 24 | m


def dec(word):
    if word & 0xFFFFFF == 0:
        return (0, 0, 0)
    return (1 if word >> 31 else 0, word & 0xFFFFFF, ((word >> 24) & 0x7F) - 64)


def to_frac(t):
    s, m, e = t
    if m == 0:
        return Fraction(0)
    v = Fraction(m) * Fraction(10) ** (e - 6)
    return -v if s else v


def trunc7(fr):
    if fr == 0:
        return (0, 0, 0)
    s = 1 if fr < 0 else 0
    a = abs(fr)
    e = 0
    while a >= Fraction(10) ** (e + 1):
        e += 1
    while a < Fraction(10) ** e:
        e -= 1
    m = int(a / Fraction(10) ** (e - 6))
    if m >= 10 ** 7:
        m //= 10
        e += 1
    return (s, m, e)


def run_prog(a, max_steps=200000000):
    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp) / "fp.bin"
        binary.write_bytes(a.bytes())
        r = subprocess.run(["dotnet", "run", "--project", str(ROOT), "--no-build", "--",
                            "--load", str(binary), "0100", "--pc", "0100", "--run",
                            "--max", str(max_steps), "--dump", f"{RES:04X}", "1000"],
                           capture_output=True, text=True, timeout=300)
    data = bytearray()
    for line in r.stdout.splitlines():
        if re.match(r"^[0-9A-F]{4}:", line):
            data.extend(bytes.fromhex(line.split(":", 1)[1]))
    return bytes(data), r.stdout + r.stderr


def batch_ops(cases):
    """cases: (opname, a_word, b_word). Returns list of (word, aux, ovf, divz)."""
    a = Asm(0x100).vars_at(0x6000)
    declare_float_workspace(a)
    ops = {"add": "fp_add", "sub": "fp_sub", "mul": "fp_mul",
           "div": "fp_div", "cmp": "fp_cmp", "neg": "fp_neg",
           "trunc": "fp_trunc"}
    for i, (op, aw, bw) in enumerate(cases):
        a.lda_i((aw >> 16) & 0xFFFF).ldb_i(aw & 0xFFFF)
        a.lda_i((bw >> 16) & 0xFFFF).sta_d("fp_fop").ldb_i(bw & 0xFFFF).stb_d("fp_fop+2")
        a.lda_i((aw >> 16) & 0xFFFF).ldb_i(aw & 0xFFFF)
        a.jsr_abs(ops[op])
        a.sta_d(RES + 8 * i).stb_d(RES + 8 * i + 2)
        a.ldab_d("fp_ovf+1").stab_d(RES + 8 * i + 4)
        a.ldab_d("fp_divz+1").stab_d(RES + 8 * i + 5)
        a.lda_i(0).sta_d("fp_ovf").sta_d("fp_divz")
    a.hlt()
    a.label("putc").ldbb_i(1).svc(0x40).rsr()
    emit_float_routines(a)
    data, log = run_prog(a)
    out = []
    for i in range(len(cases)):
        w = int.from_bytes(data[8 * i:8 * i + 4], "big")
        out.append((w, data[8 * i + 4], data[8 * i + 5]))
    return out, log



def model_addsub(op, ta, tb):
    sa, ma, ea = ta
    sb, mb, eb = tb
    if op == "sub":
        sb ^= 1
    if ea > eb:
        mb = mb // 10 ** (ea - eb) if ea - eb < 8 else 0
        eb = ea
    elif eb > ea:
        ma = ma // 10 ** (eb - ea) if eb - ea < 8 else 0
        ea = eb
    tot = (-ma if sa else ma) + (-mb if sb else mb)
    if tot == 0:
        return (0, 0, 0)
    s = 1 if tot < 0 else 0
    m = abs(tot)
    while m >= 10 ** 7:
        m //= 10
        ea += 1
    while m < 10 ** 6:
        m *= 10
        ea -= 1
    return (s, m, ea)

def model_op(op, ta, tb):
    fa, fb = to_frac(ta), to_frac(tb)
    if op in ("add", "sub"):
        return model_addsub(op, ta, tb)
    if op == "mul":
        return trunc7(fa * fb)
    if op == "div":
        if fb == 0:
            return None
        return trunc7(fa / fb)
    if op == "trunc":
        return trunc7(Fraction(int(fa)))
    if op == "neg":
        return trunc7(-fa)
    if op == "cmp":
        return (fa > fb) - (fa < fb)
    raise ValueError(op)


def check_ops(cases):
    got, log = batch_ops(cases)
    bad = []
    for (op, aw, bw), (w, ovf, divz) in zip(cases, got):
        ta, tb = dec(aw), dec(bw)
        want = model_op(op, ta, tb)
        if op == "cmp":
            g = w >> 16
            if g >= 0x8000:
                g -= 0x10000
            if g != want:
                bad.append((op, ta, tb, "cmp", want, g))
        elif want is None:
            if not divz:
                bad.append((op, ta, tb, "divz not set", w))
        elif dec(w) != want:
            bad.append((op, ta, tb, "want", want, "got", dec(w)))
    return bad, log


class FpOpsTests(unittest.TestCase):
    def test_targeted(self):
        V = lambda s, m, e: enc(s, m, e)
        cases = []
        pairs = [
            (V(0, 1000000, 0), V(0, 9999999, -1)),   # 1 + 0.9999999 alignment
            (V(0, 9999999, 0), V(0, 9999999, 0)),    # carry out of mantissa
            (V(0, 1065536, 0), V(0, 9000000, 0)),    # lo-word carry
            (V(0, 1000000, 5), V(1, 1000000, 5)),    # cancel to zero
            (V(0, 1000000, 0), V(0, 1000000, -7)),   # tiny addend lost
            (V(0, 1234567, 3), V(1, 7654321, 2)),    # mixed signs
            (V(1, 5000000, 0), V(0, 2500000, 0)),    # -5 + 2.5
            (V(0, 3333333, -1), V(0, 3000000, 0)),   # (1/3)*3 via mul below
            (V(0, 9999999, 9), V(0, 9999999, 9)),    # big mul
            (V(0, 1000000, 0), V(0, 3000000, 0)),    # 1/3
            (V(0, 2000000, 0), V(0, 3000000, 0)),    # 2/3
            (V(0, 1000000, 10), V(0, 1000000, -10)), # range
            (V(0, 5000000, -3), V(0, 5000000, -3)),  # small add
        ]
        for op in ("add", "sub", "mul", "div", "cmp"):
            for x, y in pairs:
                cases.append((op, x, y))
                cases.append((op, y, x))
        for x, y in pairs:
            cases.append(("neg", x, 0))
        bad, log = check_ops(cases)
        self.assertEqual(bad, [], str(bad[:6]) + "\n" + log[-2000:])

    def test_trunc(self):
        V = lambda s, m, e: enc(s, m, e)
        vals = [V(0, 3700000, 0), V(1, 3700000, 0), V(0, 5000000, -1),
                V(1, 9000000, -1), V(0, 1234567, 5), V(0, 9999999, 6),
                V(0, 1000000, 10), V(0, 5000000, -3), V(1, 9999999, 5),
                V(0, 1000000, 0), V(0, 9999999, -1), V(0, 1999999, 0),
                V(0, 1000000, -38), V(0, 9999999, 38), V(0, 0, 0)]
        cases = [("trunc", x, 0) for x in vals]
        rng = random.Random(777)
        for _ in range(60):
            cases.append(("trunc", enc(rng.randrange(2), rng.randrange(1000000, 10000000), rng.randrange(-12, 13)), 0))
        bad, log = check_ops(cases)
        self.assertEqual(bad, [], str(bad[:6]) + "\n" + log[-2000:])

    def test_random(self):
        rng = random.Random(20261122)
        cases = []
        for _ in range(300):
            def rv():
                return enc(rng.randrange(2), rng.randrange(1000000, 10000000),
                           rng.randrange(-20, 21))
            op = rng.choice(["add", "sub", "mul", "div", "cmp"])
            cases.append((op, rv(), rv()))
        bad, log = check_ops(cases)
        self.assertEqual(bad, [], str(bad[:6]) + "\n" + log[-2000:])



def model_print(t):
    s, m, e = t
    if m == 0:
        return "0"
    d7 = m % 10
    m6 = m // 10
    if d7 >= 5:
        m6 += 1
    if m6 == 10 ** 6:
        m6 = 100000
        e += 1
    dig = str(m6)
    if -3 <= e <= 6:
        if e >= 0:
            ip = dig[:e + 1] if e + 1 <= 6 else dig + "0" * (e + 1 - 6)
            frac = dig[e + 1:] if e + 1 < 6 else ""
            frac = frac.rstrip("0")
            out = ip + ("." + frac if frac else "")
        else:
            frac = ("0" * (-e - 1) + dig).rstrip("0")
            out = "0." + frac
    else:
        ex = e + 1
        out = "0." + dig + "E" + ("+" if ex >= 0 else "-") + str(abs(ex)).rjust(2, "0")
    return ("-" if s else "") + out


def run_print(values):
    a = Asm(0x100).vars_at(0x6000)
    declare_float_workspace(a)
    for w in values:
        a.lda_i((w >> 16) & 0xFFFF).ldb_i(w & 0xFFFF)
        a.jsr_abs("fp_print")
        a.lda_i(0x7C).jsr_abs("putc")
    a.hlt()
    a.label("putc").ldbb_i(1).svc(0x40).rsr()
    emit_float_routines(a)
    with tempfile.TemporaryDirectory() as tmp:
        binary = Path(tmp) / "fp.bin"
        binary.write_bytes(a.bytes())
        r = subprocess.run(["dotnet", "run", "--project", str(ROOT), "--no-build", "--", "--load", str(binary), "0100", "--pc", "0100", "--run", "--max", "100000000"], capture_output=True, text=True, timeout=120)
    return r.stdout


def run_parse(strings):
    a = Asm(0x100).vars_at(0x6000)
    declare_float_workspace(a)
    labels = ["str_" + str(i) for i in range(len(strings))]
    for i, lab in enumerate(labels):
        a.lda_label(lab).xfr("A", "Z")
        a.jsr_abs("fp_parse")
        a.sta_d(RES + 8 * i).stb_d(RES + 8 * i + 2)
        a.ldab_d("fp_perr+1").stab_d(RES + 8 * i + 4)
        a.lda_i(0).sta_d("fp_perr")
    a.hlt()
    a.label("putc").ldbb_i(1).svc(0x40).rsr()
    emit_float_routines(a)
    for lab, text in zip(labels, strings):
        a.label(lab).asciz(text)
    data, log = run_prog(a)
    out = []
    for i in range(len(strings)):
        w = int.from_bytes(data[8 * i:8 * i + 4], "big")
        out.append((w, data[8 * i + 4]))
    return out, log


class FpParsePrintTests(unittest.TestCase):
    def test_parse_values(self):
        strs = ["1", "2.5", "-4.5", "+2.5", ".5", "007", "1.5E3", "1E10",
                "0.000012345", "123456789", "3.14159", "9999999", "10000000",
                "0.1", "2.5E-3", "12E+2", "1E", "0", "0.0", "-0.00001", "6.02E2"]
        got, log = run_parse(strs)
        for text, (w, perr) in zip(strs, got):
            self.assertEqual(perr, 0, text)
            want = trunc7(Fraction(text.split("E")[0] if text.endswith("E") else text))
            self.assertEqual(dec(w), want, text)

    def test_parse_errors(self):
        strs = ["", "X", ".", "E5", "-", " "]
        got, log = run_parse(strs)
        for text, (w, perr) in zip(strs, got):
            self.assertEqual(perr, 1, repr(text))

    def test_print_values(self):
        vals = [(0, 0, 0), (0, 1000000, 0), (0, 2500000, 0), (0, 3333333, -1),
                (0, 1234567, 8), (0, 1000000, 10), (1, 1234567, 4), (0, 9999999, -1),
                (0, 1000000, -3), (0, 1000000, -4), (0, 1234567, 6), (0, 5000000, -3),
                (1, 9999999, 38), (0, 1000000, -38), (0, 6666667, -1), (0, 1500000, 1)]
        words = [enc(*v) for v in vals]
        out = run_print(words)
        parts = out.split("|")
        for v, got in zip(vals, parts):
            self.assertEqual(got, model_print(v), str(v))

    def test_print_random(self):
        rng = random.Random(7)
        vals = []
        for _ in range(120):
            vals.append((rng.randrange(2), rng.randrange(1000000, 10000000), rng.randrange(-30, 31)))
        out = run_print([enc(*v) for v in vals])
        parts = out.split("|")
        for v, got in zip(vals, parts):
            self.assertEqual(got, model_print(v), str(v))


class FpConvTests(unittest.TestCase):
    def run_conv(self, kind, items):
        a = Asm(0x100).vars_at(0x6000)
        declare_float_workspace(a)
        for i, it in enumerate(items):
            if kind == "fi":
                a.lda_i(it & 0xFFFF).jsr_abs("fp_from_i16")
            else:
                a.lda_i((it >> 16) & 0xFFFF).ldb_i(it & 0xFFFF).jsr_abs("fp_to_i16")
            a.sta_d(RES + 8 * i).stb_d(RES + 8 * i + 2)
        a.hlt()
        a.label("putc").ldbb_i(1).svc(0x40).rsr()
        emit_float_routines(a)
        data, log = run_prog(a)
        return [int.from_bytes(data[8 * i:8 * i + 4], "big") for i in range(len(items))]

    def test_from_i16(self):
        vals = [0, 1, -1, 2, 15, 16, 255, 4096, 32767, -32768, 1000, -9999, 30000]
        got = self.run_conv("fi", vals)
        for v, w in zip(vals, got):
            self.assertEqual(dec(w), trunc7(Fraction(v)), str(v))

    def test_to_i16(self):
        cases = [((0, 1500000, 1), 15), ((1, 2500000, 0), -2), ((0, 9999999, 6), 32767),
                 ((0, 1000000, -3), 0), ((1, 1000000, 2), -100), ((0, 3276700, 2), 327),
                 ((1, 9999999, 6), -32767), ((0, 1234567, 0), 1)]
        got = self.run_conv("ti", [enc(*c) for c, _ in cases])
        for (t, want), w in zip(cases, got):
            g = w >> 16
            if g >= 0x8000:
                g -= 0x10000
            self.assertEqual(g, want, str(t))

if __name__ == "__main__":
    unittest.main()

