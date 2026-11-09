#!/usr/bin/env python3
"""CPU6 DG-float primitive tests; run under nix develop."""
import re
import shutil
import subprocess
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from cpu6asm import Asm
from cpu6_float import declare_float_workspace, emit_float_routines

ROOT = Path(__file__).resolve().parent.parent


def integer_as_dg(value):
    """Independent exact encoding for signed 16-bit integers."""
    if not value:
        return 0
    sign = 0x80000000 if value < 0 else 0
    magnitude = abs(value)
    exponent = (magnitude.bit_length() + 3) // 4
    fraction = magnitude * (16 ** (6 - exponent))
    return sign | ((64 + exponent) << 24) | fraction


def dg_as_fraction(word):
    if word & 0xffffff == 0:
        return Fraction(0)
    exponent = ((word >> 24) & 0x7f) - 64
    value = Fraction(word & 0xffffff, 1 << 24) * Fraction(16) ** exponent
    return -value if word & 0x80000000 else value


class FormatTests(unittest.TestCase):
    def test_known_encodings(self):
        for value, word in [(0, 0), (1, 0x41100000), (-1, 0xc1100000),
                            (16, 0x42100000), (256, 0x43100000),
                            (32767, 0x447fff00), (-32768, 0xc4800000)]:
            self.assertEqual(integer_as_dg(value), word)
            self.assertEqual(dg_as_fraction(word), value)


@unittest.skipUnless(shutil.which("dotnet"), "needs dotnet")
class Cpu6FloatTests(unittest.TestCase):
    def test_signed_integer_conversion_on_cpu6(self):
        values = [0, 1, -1, 2, 15, 16, 17, 255, 256, 257,
                  4095, 4096, 4097, 32767, -32768, -32767, -16]
        a = Asm(0x100).vars_at(0x2400)
        declare_float_workspace(a)
        for i, value in enumerate(values):
            a.lda_i(value & 0xffff).jsr_abs("fp_from_i16")
            a.sta_d(0x3000 + 4 * i).stb_d(0x3002 + 4 * i)
        a.hlt()
        emit_float_routines(a)
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "fp.bin"
            binary.write_bytes(a.bytes())
            result = subprocess.run(["dotnet", "run", "--project", str(ROOT), "--no-build", "--",
                                     "--load", str(binary), "0100", "--pc", "0100", "--run",
                                     "--max", "100000", "--dump", "3000", f"{4 * len(values):04X}"],
                                    capture_output=True, text=True, check=True, timeout=60)
        data = bytearray()
        for line in result.stdout.splitlines():
            if re.match(r"^[0-9A-F]{4}:", line):
                data.extend(bytes.fromhex(line.split(":", 1)[1]))
        actual = [int.from_bytes(data[i:i + 4], "big") for i in range(0, len(data), 4)]
        self.assertEqual(actual, [integer_as_dg(v) for v in values], result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
