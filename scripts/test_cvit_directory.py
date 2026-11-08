#!/usr/bin/env python3
"""Extended and legacy cvit directory regression tests."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from hawk_put_text import dir_entries, put_text
from mkhawk import build, build_library, directory_sectors

ROOT = Path(__file__).resolve().parent.parent


class DirectoryLayoutTests(unittest.TestCase):
    def test_directory_capacity_and_pages(self):
        for count in (0, 10, 11, 24, 49, 98, 99):
            members = [(f"M{i:03}", bytes([i % 256]), 4) for i in range(count)]
            lib, pages = build_library(members)
            sectors = directory_sectors(count)
            self.assertEqual(lib[10:14], b"DX" + sectors.to_bytes(2, "big"))
            if members:
                self.assertEqual(pages["M000"], sectors * 2)
            self.assertEqual(lib[16 + count * 16:18 + count * 16], b"\x84\x8d")
            for name, data, _ in members:
                self.assertEqual(lib[pages[name] * 200:pages[name] * 200 + 1], data)

    def test_packed_and_padded_host_tools_across_sectors(self):
        for stride in (400, 512):
            with self.subTest(stride=stride), tempfile.TemporaryDirectory() as tmp:
                image, _ = build([], [], "TEST", 0x800, 0x800, stride, boot=False)
                path = Path(tmp) / "disk.img"
                source = Path(tmp) / "text.txt"
                path.write_bytes(image)
                source.write_bytes(b"X" * 450)
                for i in range(26):
                    put_text(path, f"M{i:02}", source)
                img = path.read_bytes()
                entries = list(dir_entries(img, stride, 0x20))
                self.assertEqual([e[1] for e in entries], [f"M{i:02}" for i in range(26)])
                page = entries[-1][2]
                start = (0x20 + page // 2) * stride
                self.assertEqual(img[start:start + 400], b"X" * 400)
                self.assertEqual(img[start + stride:start + stride + 50], b"X" * 50)
                if stride == 512:
                    self.assertEqual(img[start + 400:start + 512], b"\xff" * 112)


@unittest.skipUnless(shutil.which("dotnet") and (ROOT / "out/os.img").exists(), "needs dotnet and built out/os.img")
class DirectoryIntegrationTests(unittest.TestCase):
    def test_catalog_type_and_guest_create_after_sector_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "os.img"
            source = Path(tmp) / "text.txt"
            shutil.copyfile(ROOT / "out/os.img", image)
            source.write_text("DIRECTORY TEST\n")
            for i in range(17):
                put_text(image, f"M{i:02}", source)
            result = subprocess.run([str(ROOT / "scripts/bis"), "--hawk", str(image), "--run", "--max", "20000000", "--type", r"H0\rCAT\rTYPE M16\r.CED NEWFILE\rA\rHELLO\r.\rW\rQ\rCAT\rTYPE NEWFILE\rQ\r"], capture_output=True, text=True, check=True, timeout=60)
            self.assertIn("M16", result.stdout)
            self.assertIn("DIRECTORY TEST", result.stdout)
            self.assertIn("NEWFILE", result.stdout)
            self.assertIn("HELLO", result.stdout)
            entries = list(dir_entries(image.read_bytes(), 512, 0x20))
            self.assertIn("NEWFILE", [e[1] for e in entries])


if __name__ == "__main__":
    unittest.main()
