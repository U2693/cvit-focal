#!/usr/bin/env python3
"""End-to-end TYPE boundary regression on a disposable Hawk image."""
import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from hawk_put_text import put_text

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("dotnet") and (ROOT / "out/os.img").exists(), "needs dotnet and built out/os.img")
class TypeBoundaryTests(unittest.TestCase):
    def test_text_member_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "os.img"
            source = Path(tmp) / "input.txt"
            shutil.copyfile(ROOT / "out/os.img", image)
            sizes = (0, 1, 199, 200, 201, 399, 400, 401, 800)
            expected = {}
            for size in sizes:
                name = f"T{size}"
                content = "".join(chr(65 + i % 26) for i in range(size))
                source.write_text(content)
                with contextlib.redirect_stdout(io.StringIO()):
                    put_text(image, name, source)
                expected[name] = content
            commands = "".join(f"TYPE {name}\\r" for name in expected)
            run = subprocess.run([str(ROOT / "scripts/bis"), "--hawk", str(image), "--run", "--max", "40000000", "--type", "H0\\r" + commands + "Q\\r"], capture_output=True, text=True, check=True, timeout=60)
            output = run.stdout.replace("\r", "")
            for name, content in expected.items():
                with self.subTest(name=name):
                    actual = output.split(f"]TYPE {name}\n", 1)[1].split("\n]", 1)[0]
                    self.assertEqual(actual, "\n" + content + "\n")


if __name__ == "__main__":
    unittest.main()
