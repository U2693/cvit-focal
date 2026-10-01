#!/usr/bin/env python3
"""Reconstruct a Centurion Disk-6-style flat image from an HxC .hfe image.

This is intentionally tuned for the Centurion HFE dumps in ../CenturionComputer.
It decodes each HFE track side to bytes, extracts sector payloads at the
observed fixed offsets, and applies CentOpSys boot/volume/catalog fixups needed
for a logical Disk-6 image suitable for biscvit.

Examples:
  scripts/hfe_to_disk6.py ../CenturionComputer/Drives/Floppy/FluxReading/CentOpSys.hfe roms/cops.img --side 0
  scripts/hfe_to_disk6.py ../CenturionComputer/Drives/Floppy/FluxReading/CentOpSys.hfe /tmp/cops_2h.img --all-sides
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

SECTOR_SIZE = 400
SECTORS_PER_TRACK = 20
PAYLOAD_OFFSET = 75
# Standard formatted tracks in CentOpSys have 400-byte payloads separated by
# ~109 bytes of header/gap. Starts alternate by 509/510 decoded bytes.
NOMINAL_STARTS = [75, 584, 1094, 1603, 2112, 2622, 3131, 3641, 4150, 4659,
                  5169, 5678, 6187, 6697, 7206, 7716, 8225, 8734, 9244, 9753]
# Disk-6 volume record used by FDIPL.  The key/offset fields decode to
# directory sector 0x0010, matching the catalog found on CentOpSys T0/S0.
DISK6_VOLUME_RECORD = bytes.fromhex('78 c5 00 00 ef 2c e4 54 ff ff')
CENTOPS_T0_CATALOG_OFFSET = 5312


def decode_track_side(hfe: bytes, track_table: int, track: int, side: int, phase: int) -> bytes:
    off_blocks, length = struct.unpack_from('<HH', hfe, track_table + track * 4)
    raw = hfe[off_blocks * 512:off_blocks * 512 + length]

    # HFE alternates side data in 256-byte chunks inside each 512-byte block.
    sidebytes = b''.join(
        raw[i + side * 256:i + (side + 1) * 256]
        for i in range(0, len(raw), 512)
    )

    bits = [(byte >> bit) & 1 for byte in sidebytes for bit in range(8)]
    out = bytearray()
    for k in range(phase, len(bits) - 16, 16):
        value = 0
        for j in range(8):
            value = (value << 1) | bits[k + j * 2 + 1]
        out.append(value)
    return bytes(out)


def find_payload_starts(decoded: bytes) -> list[int]:
    """Find sector payload starts using the observed FF-gap/header pattern."""
    starts: list[int] = []
    i = 0
    while i < len(decoded):
        if decoded[i] != 0xff:
            i += 1
            continue
        j = i
        while j < len(decoded) and decoded[j] == 0xff:
            j += 1
        if j - i >= 20 and j + 8 + SECTOR_SIZE <= len(decoded):
            # Payload starts after an 8-byte sector header.  There are often two
            # close FF runs before a sector; keep the later candidate.
            candidate = j + 8
            if starts and candidate - starts[-1] < 100:
                starts[-1] = candidate
            else:
                starts.append(candidate)
        i = j
    return starts[:SECTORS_PER_TRACK]


def payload_score(payload: bytes) -> tuple[float, int]:
    """Heuristic for choosing between two plausible bit phases.

    The wrong phase commonly looks like the right data shifted by a nibble and
    has an unusually high fraction of non-zero bytes ending in low nibble 0.
    """
    nz = [b for b in payload[:128] if b != 0]
    if not nz:
        return (0.0, 0)
    low_zero = sum(1 for b in nz if (b & 0x0f) == 0)
    penalty = 0.0
    if payload[0] != 0 and payload[0] < 0x80:
        penalty += 1.0
    # A common bad-phase artifact on object/data sectors is a tiny length byte
    # such as 07 where the alternate phase shows the expected 70/78-ish record.
    if payload[0] == 0 and payload[1] == 0x07:
        penalty += 0.5
    return (penalty + low_zero / len(nz), -len(nz))


def extract_track(decoded: bytes, track: int, side: int, verbose: bool) -> bytes:
    # Track 0 side 0 of CentOpSys is a bootstrap/volume track without the
    # normal per-sector FF/header cadence.  Sectors 0..9 hold the IPL area,
    # logical sector 14 is the Disk-6 volume record, and logical sector 16
    # is the catalog found later in the decoded stream.
    if track == 0 and side == 0:
        out = bytearray(SECTORS_PER_TRACK * SECTOR_SIZE)
        for i in range(10):
            start = PAYLOAD_OFFSET + i * SECTOR_SIZE
            out[i * SECTOR_SIZE:(i + 1) * SECTOR_SIZE] = decoded[start:start + SECTOR_SIZE].ljust(SECTOR_SIZE, b'\0')
        out[14 * SECTOR_SIZE:14 * SECTOR_SIZE + len(DISK6_VOLUME_RECORD)] = DISK6_VOLUME_RECORD
        out[16 * SECTOR_SIZE:17 * SECTOR_SIZE] = decoded[CENTOPS_T0_CATALOG_OFFSET:CENTOPS_T0_CATALOG_OFFSET + SECTOR_SIZE].ljust(SECTOR_SIZE, b'\0')
        if verbose:
            print(f'T{track:02d} S{side}: centops-t0s0 boot=0..9 vol=14 catalog=16')
        return bytes(out)

    return extract_normal_track([(0, decoded)], track, side, verbose)


def extract_normal_track(decoded_by_phase: list[tuple[int, bytes]], track: int, side: int, verbose: bool) -> bytes:
    # Normal tracks are laid out at fixed offsets.  Do not use FF-gap scanning
    # here: real payloads can contain long FF runs, which creates false sector
    # starts and corrupts later sectors on data-heavy tracks.
    if verbose:
        notes: list[str] = []
        for phase, decoded in decoded_by_phase:
            gaps = find_payload_starts(decoded)
            suffix = '' if gaps == NOMINAL_STARTS else f' gaps={len(gaps)} differs'
            notes.append(f'phase={phase}{suffix}')
        print(f'T{track:02d} S{side}: nominal starts={NOMINAL_STARTS[:3]}... count={len(NOMINAL_STARTS)} ({"; ".join(notes)})')

    out = bytearray()
    phase_counts: dict[int, int] = {}
    for start in NOMINAL_STARTS:
        candidates: list[tuple[tuple[float, int], int, bytes]] = []
        for phase, decoded in decoded_by_phase:
            payload = decoded[start:start + SECTOR_SIZE].ljust(SECTOR_SIZE, b'\0')
            candidates.append((payload_score(payload), phase, payload))
        score, phase, payload = min(candidates, key=lambda c: c[0])
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        out.extend(payload)

    if verbose and len(decoded_by_phase) > 1:
        counts = ' '.join(f'phase{phase}={count}' for phase, count in sorted(phase_counts.items()))
        print(f'T{track:02d} S{side}: selected {counts}')
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('src', type=Path)
    ap.add_argument('dst', type=Path)
    ap.add_argument('--side', type=int, default=0, help='convert only this side (default: 0)')
    ap.add_argument('--all-sides', action='store_true', help='write track/head/sector order for all HFE sides')
    ap.add_argument('--phase', type=int, default=None, help='force one decode phase for all tracks')
    ap.add_argument('--boot-phase', type=int, default=6, help='decode phase for CentOpSys track 0 side 0 (default: 6)')
    ap.add_argument('--normal-phase', type=int, default=14, help='alternate decode phase for normal-track sector heuristic (default: 14)')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    hfe = args.src.read_bytes()
    if hfe[:8] != b'HXCPICFE':
        raise SystemExit('not an HFE image (missing HXCPICFE signature)')

    tracks = hfe[9]
    sides = hfe[10]
    track_table = struct.unpack_from('<H', hfe, 18)[0] * 512
    selected_sides = range(sides) if args.all_sides else [args.side]

    image = bytearray()
    for track in range(tracks):
        for side in selected_sides:
            if args.phase is not None:
                decoded = decode_track_side(hfe, track_table, track, side, args.phase)
                if args.verbose:
                    print(f'T{track:02d} S{side}: forced phase={args.phase}')
                image.extend(extract_track(decoded, track, side, args.verbose))
            elif track == 0 and side == 0:
                decoded = decode_track_side(hfe, track_table, track, side, args.boot_phase)
                if args.verbose:
                    print(f'T{track:02d} S{side}: phase={args.boot_phase}')
                image.extend(extract_track(decoded, track, side, args.verbose))
            else:
                decoded_by_phase = [
                    (args.boot_phase, decode_track_side(hfe, track_table, track, side, args.boot_phase)),
                    (args.normal_phase, decode_track_side(hfe, track_table, track, side, args.normal_phase)),
                ]
                image.extend(extract_normal_track(decoded_by_phase, track, side, args.verbose))

    args.dst.parent.mkdir(parents=True, exist_ok=True)
    args.dst.write_bytes(image)
    heads = sides if args.all_sides else 1
    print(f'wrote {args.dst}: {len(image)} bytes ({tracks} tracks, {heads} head(s), {SECTORS_PER_TRACK} sectors, {SECTOR_SIZE} bytes/sector)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
