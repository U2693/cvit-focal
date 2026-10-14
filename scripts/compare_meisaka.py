#!/usr/bin/env python3
"""Run biscvit's JSONL oracle server against ../cpu6-oracle's Meisaka backend."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE = (ROOT / ".." / "cpu6-oracle").resolve()

SMOKE = [
    (0, [0x01]),          # NOP
    (0, [0x00]),          # HALT
    (0, [0x02]),          # SF
    (4, [0x14, 0xFE]),    # BZ -2
]

def smoke_cases() -> str:
    regs = ["0000"] * 5 + ["FFFE", "0000", "0000"]
    lines = []
    for flags, bs in SMOKE:
        lines.append(json.dumps({"op":"step","state":{"pc":256,"ipl":0,"flags":flags,"regs":regs,
            "memory":[{"address":256,"bytes":" ".join(f"{b:02X}" for b in bs)}]}}))
    return "\n".join(lines) + "\n"

def run(cmd, data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, input=data, text=True, capture_output=True)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="?", help="JSONL cases; defaults to built-in smoke cases")
    ap.add_argument("--keep", action="store_true", help="keep /tmp reference and implementation outputs")
    args = ap.parse_args()

    if not (ORACLE / "meisaka-wrapper.js").exists():
        raise SystemExit(f"missing {ORACLE}; clone/build ../cpu6-oracle first")
    if not (ORACLE / "build" / "meisaka-core.js").exists():
        raise SystemExit("missing ../cpu6-oracle/build/meisaka-core.js; run MEISAKA_SOURCE=... npm run build-meisaka in ../cpu6-oracle")

    cases = Path(args.cases).read_text() if args.cases else smoke_cases()
    ref = run(["node", str(ORACLE / "meisaka-wrapper.js")], cases)
    if ref.returncode:
        sys.stderr.write(ref.stderr); return ref.returncode
    impl = run(["dotnet", "run", "--no-build", "--", "--oracle-server"], cases)
    if impl.returncode:
        sys.stderr.write(impl.stderr); return impl.returncode

    ref_path = Path("/tmp/biscvit-meisaka-reference.jsonl")
    impl_path = Path("/tmp/biscvit-meisaka-implementation.jsonl")
    ref_path.write_text(ref.stdout); impl_path.write_text(impl.stdout)
    cmp = run(["python3", str(ORACLE / "compare.py"), "--reference", str(ref_path), "--implementation", str(impl_path)])
    sys.stdout.write(cmp.stdout); sys.stderr.write(cmp.stderr)
    if not args.keep and cmp.returncode == 0:
        ref_path.unlink(missing_ok=True); impl_path.unlink(missing_ok=True)
    return cmp.returncode

if __name__ == "__main__":
    raise SystemExit(main())
