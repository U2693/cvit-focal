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
    def test_shared_session_transcript(self):
        session = (ROOT / "testdata/focal-common.session").read_text().splitlines()
        self.assertEqual(session[-1], "QUIT")
        out = focal(*session[:-1])
        transcript = out[out.index("*T 2+3*4"):out.index("\n]Q")].strip()
        expected = (ROOT / "testdata/focal-common.expected").read_text().strip()
        self.assertEqual(transcript, expected)

    def test_arithmetic(self):
        out = focal("T 2+3*4,!", "T (2+3)*4,!", "T -5/2,!", "T 7-10,!", "T 100/7,\"r\",100-7*14,!")
        for want in ("\n14\n", "\n20\n", "\n-2.5\n", "\n-3\n", "\n14.2857r2\n"):
            self.assertIn(want, out)

    def test_powers(self):
        out = focal("T 2^10,!,2^3^2,!,-2^2,!,(-2)^3,!", "T 2^-1", "T 7,!")
        for value in ("1024", "512", "-4", "-8", "7"):
            self.assertIn("\n" + value + "\n", out)
        self.assertIn("\n0.5", out)

    def test_functions(self):
        out = focal("T FABS(-4),!,FABS(2.5),!", "T FSGN(-2),!,FSGN(0),!,FSGN(7),!",
                    "T FITR(-3.7),!,FITR(3.9),!,FITR(123456.7),!,FITR(-0.5),!", "T FSQT(4),!,FSQT(2),!,FSQT(0),!,FSQT(152399025),!",
                    "T FSQT(FABS(-16)),!", "T 1+FSQT(9)*2,!")
        for want in ("\n4\n", "\n2.5\n", "\n-1\n", "\n0\n", "\n1\n", "\n-3\n", "\n3\n",
                     "\n123456\n", "\n2\n", "\n1.41421\n", "\n12345\n", "\n7\n"):
            self.assertIn(want, out)
        self.assertIn("?FUN", focal("T FSQT(-1)"))
        self.assertIn("?FUN", focal("T FZZ(3)"))

    def test_subscripts(self):
        out = focal("S X(1)=10", "S X(2)=20", "T X(1)+X(2),!", "S A=5", "T A,!,A(0),!",
                    "S X(1+1)=99", "T X(2),!", "T Q(7),!", "S X(-2)=-8", "T X(-2),!",
                    "S X(FITR(2.9))=1", "T X(2.9),!", "FOR X(1)=1,3;T X(1),\" \"")
        for want in ("\n30\n", "\n5\n", "\n99\n", "\n0\n", "\n-8\n", "\n1\n"):
            self.assertIn(want, out)
        self.assertIn("1 2 3 ", out)
        prog = focal("1.1 F I=1,3;S S(I)=I*I", "1.2 F I=1,3;T S(I),\" \"", "G")
        self.assertIn("1 4 9 ", prog)
        full = focal("1.1 F I=1,70;S V(I)=I", "G")
        self.assertIn("?VAR", full)

    def test_variables_and_multiple_statements(self):
        self.assertIn("\n49\n", focal("S A=7;T A*A,!"))

    def test_program_loop_with_if(self):
        out = focal("1.1 S X=1", "1.2 T X,\" \"", "1.3 S X=X+1", "1.4 I (X-6) 1.2,1.5,1.5", "1.5 T !", "G")
        self.assertIn("1 2 3 4 5 \n", out)

    def test_write_lists_sorted_and_normalised(self):
        out = focal("2.1 T 2", "1.1 T 1", "W")
        self.assertRegex(out, r"1\.10 T 1\n2\.10 T 2\n")

    def test_write_group_and_line(self):
        out = focal("1.1 T 11", "1.2 T 12", "2.1 T 21", "W 1", "W 2.1")
        group = out.split("*W 1\n", 1)[1].split("*W 2.1\n", 1)[0]
        line = out.split("*W 2.1\n", 1)[1]
        self.assertIn("1.10 T 11", group)
        self.assertIn("1.20 T 12", group)
        self.assertNotIn("2.10", group)
        self.assertIn("2.10 T 21", line)
        self.assertNotIn("1.10", line)

    def test_for_step_and_negative_step(self):
        out = focal("FOR I=1,5; T I*I,\" \"", "FOR J=10,-3,1;T J,\" \"")
        self.assertIn("1 4 9 16 25 ", out)
        self.assertIn("10 7 4 1 ", out)

    def test_do_group_and_line_and_return(self):
        out = focal("2.1 T \"SUB\",!", "2.2 R", "2.3 T \"NOT REACHED\"", "3.1 D 2;D 2.1", "GO 3.1")
        ran = out.split("GO 3.1")[1]
        self.assertEqual(ran.count("SUB"), 2)
        self.assertNotIn("NOT REACHED", ran)

    def test_f_is_a_variable(self):
        # Regression: var_ref once banned the letter F outright (a stage-2
        # guard for the F-functions), which killed any program using F as
        # a variable -- e.g. the calendar's mode flag.  F must behave like
        # any other letter, as value, flag and subscripted variable.
        self.assertIn("\n3\n", focal("S F=3;T F,!"))
        self.assertIn("\n9\n", focal("S F(2)=9;T F(2),!"))
        out = focal('1.10 S F=1;D 9', '9.10 I (F) 9.9,9.9;T "NO",!', '9.90 T "YES",!', 'G')
        self.assertIn("YES", out)

    def test_functions_still_work_with_f_variable(self):
        # The disambiguation is by full name plus '(': the four functions
        # keep working, including nested, alongside the variable F.
        self.assertIn("\n3\n", focal("T FABS(-3),!"))
        self.assertIn("\n-1\n", focal("T FSGN(-3),!"))
        self.assertIn("\n3\n", focal("T FITR(3.7),!"))
        self.assertIn("\n4\n", focal("T FSQT(16),!"))
        self.assertIn("\n1\n", focal("T FABS(FSGN(-2)),!"))

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
