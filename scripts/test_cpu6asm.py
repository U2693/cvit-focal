#!/usr/bin/env python3
"""Host-side tests for cpu6asm and (if dotnet is available) the emulator's MULU/DIVU.

  python3 scripts/test_cpu6asm.py
"""
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cpu6asm import Asm, AsmError

ROOT = Path(__file__).parent.parent


class AsmTests(unittest.TestCase):
    def test_short_branch(self):
        a = Asm(0x100); a.label("t").bz("t")
        self.assertEqual(a.bytes(), bytes([0x14, 0xFE]))

    def test_branch_relaxes_when_far(self):
        a = Asm(0x100)
        a.bz("far").ds(200).label("far").hlt()
        out = a.bytes()
        self.assertEqual(out[:3], bytes([0x15, 3, 0x71]))      # BNZ +3 ; JMP far
        target = (out[3] << 8) | out[4]
        self.assertEqual(target, a.labels["far"])
        self.assertEqual(out[target - 0x100], 0x00)            # lands on HLT

    def test_backward_far_branch_and_jmp_jsr(self):
        a = Asm(0x100)
        a.label("top").ds(300).jmp("top").jsr("top").bl("top")
        out = a.bytes()
        self.assertEqual(out[300], 0x71)                  # jmp -> jmp abs
        self.assertEqual(out[303], 0x79)                  # jsr -> jsr abs
        self.assertEqual(out[306], 0x11)                  # bl -> bnc over jmp abs
        self.assertEqual(out[307], 3)

    def test_relaxation_cascades(self):
        # The first branch fits while the second is short; the second must relax
        # (far target), which pushes "x" out of the first branch's range.
        a = Asm(0)
        a.bz("x").ds(123).bz("far").label("x").ds(200).label("far").hlt()
        out = a.bytes()
        self.assertEqual(out[0], 0x15)                         # first branch relaxed (BNZ over JMP)
        self.assertEqual(out[2], 0x71)

    def test_symbol_offsets(self):
        a = Asm(0x100)
        a.ldb_i("t-2").label("t").hlt()
        self.assertEqual(a.bytes(), bytes([0xD0, 0x01, 0x01, 0x00]))

    def test_symbols_and_vars(self):
        a = Asm(0x200).vars_at(0x2400)
        self.assertEqual(a.var("V1"), 0x2400)
        self.assertEqual(a.var("V2", 4), 0x2402)
        a.equ("K", 0x1234)
        a.lda_d("V2").ldb_i("K").lda_label("end").label("end")
        self.assertEqual(a.bytes(), bytes([0x91, 0x24, 0x02, 0xD0, 0x12, 0x34, 0x90, 0x02, 0x09]))

    def test_errors(self):
        with self.assertRaises(AsmError):
            Asm(0).jmp_abs("nowhere").bytes()
        with self.assertRaises(AsmError):
            Asm(0).label("a").label("a")

    def test_data_directives(self):
        a = Asm(0x10)
        a.db(1, 2).dw(0xABCD).asciz("hi").align(4, 0xEE).db(b"\x07")
        self.assertEqual(a.bytes(), bytes([1, 2, 0xAB, 0xCD, 0x68, 0x69, 0, 0xEE, 7]))

    def test_register_encodings(self):
        a = Asm(0)
        a.mulu("A", "B").divu("A", "B").xfr("A", "Z").inr("Z", 16).dcrb("BL").push("AL", 2).pop("AL", 2)
        self.assertEqual(a.bytes(), bytes([0x77, 0x02, 0x78, 0x02, 0x55, 0x08, 0x30, 0x8F, 0x21, 0x30, 0x7E, 0x11, 0x7F, 0x11]))

    def test_indexed_encodings(self):
        a = Asm(0)
        a.ldab_x("Z", "+").stab_x("Y", "+").ldab_x("Z", disp=5).lda_x("Y", "-", 2, indirect=True)
        self.assertEqual(a.bytes(), bytes([0x85, 0x81, 0xA5, 0x61, 0x85, 0x88, 5, 0x95, 0x6E, 2]))
        self.assertEqual(Asm(0).ldab_zinc().bytes(), bytes([0x85, 0x81]))

    def test_compare_helpers(self):
        self.assertEqual(Asm(0).cmp_al(0x0D).bytes(), bytes([0xC0, 0x0D, 0x49]))
        self.assertEqual(Asm(0).cmp_ax(0x1234).bytes(), bytes([0xD0, 0x12, 0x34, 0x59]))

    def test_listing_and_symbols(self):
        a = Asm(0x100)
        a.label("start").nop().bz("start")
        self.assertIn("start:", a.listing())
        self.assertEqual(a.symbols(), [(0x100, "start")])


@unittest.skipUnless(shutil.which("dotnet"), "dotnet not available")
class EmuTests(unittest.TestCase):
    @staticmethod
    def run_prog(build):
        a = Asm(0x100); build(a); a.hlt()
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(a.bytes())
        env = dict(os.environ, DOTNET_ROLL_FORWARD="Major")
        out = subprocess.run(["dotnet", "run", "--project", str(ROOT), "--", "--load", f.name, "0100",
                              "--pc", "0100", "--run", "--regs", "--max", "1000"],
                             capture_output=True, text=True, env=env).stdout
        os.unlink(f.name)
        regs = dict(re.findall(r"\b([A-Z]{2})=([0-9A-F]{4})", out))
        return {k: int(v, 16) for k, v in regs.items()}, out

    # Expected values follow the Centurion optest07.asm comments for MUL (0x77) and DIV (0x78).
    def regs(self, build):
        r, out = self.run_prog(build)
        return r, re.search(r"FLAGS=(\S+)", out).group(1)

    def test_mul_reg_reg_even_dst(self):          # MUL B,A: B*A -> A,B
        r, _ = self.regs(lambda a: a.lda_i(0x3003).ldb_i(6).mulu("B", "A"))
        self.assertEqual((r["AX"], r["BX"]), (0x0001, 0x2012))

    def test_mul_reg_reg_odd_dst_keeps_low_only(self):   # MUL A,B: A*B -> B
        r, _ = self.regs(lambda a: a.lda_i(0x3003).ldb_i(6).mulu("A", "B"))
        self.assertEqual((r["AX"], r["BX"]), (0x3003, 0x2012))

    def test_mul_imm(self):                       # MUL= 6,A ; MUL= 0x3003,A,B
        r, _ = self.regs(lambda a: a.lda_i(0x3003).mul_imm(6, "A"))
        self.assertEqual((r["AX"], r["BX"]), (0x0001, 0x2012))
        r, _ = self.regs(lambda a: a.lda_i(6).mul_imm(0x3003, "A", "B"))
        self.assertEqual((r["AX"], r["BX"]), (6, 0x2012))

    def test_mul_mem_and_indexed(self):
        def prog(a):
            a.lda_i(256).mul_mem("W", "A").jmp("end").label("W").dw(0x3003).label("end")
        r, _ = self.regs(prog)
        self.assertEqual((r["AX"], r["BX"]), (0x0030, 0x0300))
        def prog2(a):                                         # MUL- B,7,A: *(B+7) * A
            a.lda_i(256).ldb_i("W-7").mul_idx("B", 7, "A").jmp("end").label("W").dw(0x3003).label("end")
        r, _ = self.regs(prog2)
        self.assertEqual((r["AX"], r["BX"]), (0x0030, 0x0300))

    def test_div_reg_reg(self):                   # DIV B,A: A / B -> B, A % B -> A
        r, _ = self.regs(lambda a: a.lda_i(13).ldb_i(6).divu("B", "A"))
        self.assertEqual((r["AX"], r["BX"]), (1, 2))

    def test_div_reg_reg_odd_dst(self):           # DIV A,B: B / A -> B
        r, _ = self.regs(lambda a: a.lda_i(6).ldb_i(13).divu("A", "B"))
        self.assertEqual((r["AX"], r["BX"]), (6, 2))

    def test_div_imm(self):                       # DIV= 6,A ; DIV= 6,A,B
        r, _ = self.regs(lambda a: a.lda_i(13).div_imm(6, "A"))
        self.assertEqual((r["AX"], r["BX"]), (1, 2))
        r, _ = self.regs(lambda a: a.lda_i(13).div_imm(6, "A", "B"))
        self.assertEqual((r["AX"], r["BX"]), (13, 2))

    def test_div_exact_sets_link(self):
        r, flags = self.regs(lambda a: a.lda_i(12).div_imm(6, "A"))
        self.assertEqual((r["AX"], r["BX"]), (0, 2))
        self.assertIn("C", flags)
        _, flags = self.regs(lambda a: a.lda_i(13).div_imm(6, "A"))
        self.assertNotIn("C", flags)

    def test_div_mem_and_indexed(self):
        def prog(a):
            a.lda_i(0x0205).div_mem("W", "A").jmp("end").label("W").dw(0x0100).label("end")
        r, _ = self.regs(prog)
        self.assertEqual((r["AX"], r["BX"]), (5, 2))          # 0x205 / 0x100
        def prog2(a):                                         # DIV- B,7,A: A / *(B+7)
            a.lda_i(0x0608).ldb_i("W-7").div_idx("B", 7, "A").jmp("end").label("W").dw(0x0100).label("end")
        r, _ = self.regs(prog2)
        self.assertEqual((r["AX"], r["BX"]), (8, 6))

    def test_relaxed_branch_runs(self):
        def prog(a):
            a.lda_i(0).bz("far").ds(200, 0x01).label("far").lda_i(0x55)   # skipped NOP padding
        r, _ = self.run_prog(prog)
        self.assertEqual(r["AX"], 0x55)


if __name__ == "__main__":
    unittest.main()
