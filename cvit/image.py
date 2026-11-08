import subprocess
import sys
from pathlib import Path

from cvit.constants import PAGE
from mkhawk import directory_sectors


def alloc_pages(data_len):
    """SYSTEM library page allocation increment used by mkhawk.py."""
    return max(2, ((data_len + PAGE - 1) // PAGE + 1) & ~1)


def member_name(path):
    n = path.stem.upper()
    assert 0 < len(n) <= 10, f"bad member name {path.name}: {n}"
    return n


def collect_members(system_root, generated):
    """Return mkhawk SYSTEM members from every file in system_root, with boot-critical order."""
    priority = ["KERNEL", "WELCOME", "BASIC", "CED", "TEST", "ZEP"]
    return collect_library_members(system_root, generated, priority, last=["COMMAND"])


def collect_library_members(library_root, generated=None, priority=None, last=None):
    """Return mkhawk library members from regular files in library_root."""
    generated = generated or {}
    priority = priority or []
    last = set(last or [])
    files = {member_name(p): p for p in library_root.iterdir() if p.is_file()}
    for fname in generated:
        files[member_name(Path(fname))] = library_root / fname
    names = set(files)
    ordered = [n for n in priority if n in names]
    ordered += sorted(n for n in names if n not in set(priority) | last)
    ordered += [n for n in last if n in names]
    members = []
    for n in ordered:
        p = files[n]
        data = generated[p.name] if p.name in generated else p.read_bytes()
        members.append((n, p, data))
    return members


def member_pages(members):
    pages, start = {}, directory_sectors(len(members)) * 2
    for n, _p, data in members:
        pages[n] = start
        start += alloc_pages(len(data))
    return pages


def write_system_members(system_root, generated):
    system_root.mkdir(parents=True, exist_ok=True)
    for fname, data in generated.items():
        (system_root / fname).write_bytes(data)


def pack_hawk_image(root, members, output, help_members=None):
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(root / "scripts/mkhawk.py"), str(output), "--force"]
    for n, p, _data in members:
        cmd += ["--member", f"{n}={p}"]
    for n, p, _data in help_members or []:
        cmd += ["--help-member", f"{n}={p}"]
    subprocess.check_call(cmd)
