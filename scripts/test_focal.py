#!/usr/bin/env python3
"""End-to-end FOCAL tests: boot out/os.img headless, RUN FOCAL, feed lines, check output.

  python3 scripts/mk_test_os.py && python3 scripts/test_focal.py
"""
import os, re, shutil, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent


def focal(*lines):
    keys = "H0\\rRUN FOCAL\\r" + "".join(l.replace("\\", "\\\\") + "\\r" for l in lines) + "QUIT\\rQ\\r"
    env = dict(os.environ, DOTNET_ROLL_FORWARD="Major")
    out = subprocess.run([str(ROOT / "scripts/bis"), "--hawk", str(ROOT / "out/os.img"), "--run",
                          "--max", "40000000", "--type", keys], capture_output=True, text=True, env=env).stdout
    return out.split("CVIT FOCAL V0.1", 1)[1].replace("\r", "")


@unittest.skipUnless(shutil.which("dotnet") and (ROOT / "out/os.img").exists(), "needs dotnet and out/os.img")
class FocalTests(unittest.TestCase):
    def test_arithmetic(self):
        out = focal("T 2+3*4,!", "T (2+3)*4,!", "T -5/2,!", "T 7-10,!", "T 100/7,\"r\",100-7*14,!")
        for want in ("\n14\n", "\n20\n", "\n-2\n", "\n-3\n", "\n14r2\n"):
            self.assertIn(want, out)

    def test_variables_and_multiple_statements(self):
        self.assertIn("\n49\n", focal("S A=7;T A*A,!"))

    def test_program_loop_with_if(self):
        out = focal("1.1 S X=1", "1.2 T X,\" \"", "1.3 S X=X+1", "1.4 I (X-6) 1.2,1.5,1.5", "1.5 T !", "G")
        self.assertIn("1 2 3 4 5 \n", out)

    def test_write_lists_sorted_and_normalised(self):
        out = focal("2.1 T 2", "1.1 T 1", "W")
        self.assertRegex(out, r"1\.10 T 1\n2\.10 T 2\n")

    def test_for_step_and_negative_step(self):
        out = focal("FOR I=1,5; T I*I,\" \"", "FOR J=10,-3,1;T J,\" \"")
        self.assertIn("1 4 9 16 25 ", out)
        self.assertIn("10 7 4 1 ", out)

    def test_do_group_and_line_and_return(self):
        out = focal("2.1 T \"SUB\",!", "2.2 R", "2.3 T \"NOT REACHED\"", "3.1 D 2;D 2.1", "GO 3.1")
        ran = out.split("GO 3.1")[1]
        self.assertEqual(ran.count("SUB"), 2)
        self.assertNotIn("NOT REACHED", ran)

    def test_ask(self):
        out = focal("1.1 A \"N? \",N", "1.2 F I=1,N;T I*I,!", "G", "3")
        self.assertIn("N? 3\n1\n4\n9\n", out)

    def test_delete_line_and_erase(self):
        out = focal("1.1 T 1", "1.2 T 2", "1.1", "W", "E", "W")
        self.assertNotIn("1.10", out)
        self.assertIn("1.20 T 2", out)

    def test_errors_recover(self):
        out = focal("T 1/0", "S Z=", "T 5,!")
        self.assertIn("?DIV0", out)
        self.assertIn("?SYNTAX", out)
        self.assertIn("\n5\n", out)

    def test_quit_returns_to_cvit(self):
        env = dict(os.environ, DOTNET_ROLL_FORWARD="Major")
        out = subprocess.run([str(ROOT / "scripts/bis"), "--hawk", str(ROOT / "out/os.img"), "--run", "--max", "20000000",
                              "--type", "H0\\rRUN FOCAL\\rQUIT\\rRUN HELLO\\rQ\\r"], capture_output=True, text=True, env=env).stdout
        self.assertIn("HELLO FROM /SYSTEM/HELLO", out)


if __name__ == "__main__":
    unittest.main()
