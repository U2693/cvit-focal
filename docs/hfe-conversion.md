# HFE conversion notes

`CentOpSys.hfe` is an HxC floppy-emulator image from the CenturionComputer tree:

```text
../CenturionComputer/Drives/Floppy/FluxReading/CentOpSys.hfe
```

The HFE header identifies it as an HFE v1-style image:

- signature: `HXCPICFE`
- tracks: `77`
- sides: `2`
- track lookup table: header value `1`, i.e. byte offset `0x200`

## Centurion decode used so far

For this image, useful bytes can be recovered with this experimental decode:

1. Read each track offset/length pair from the HFE track table.
2. HFE track data is split into alternating 256-byte chunks per side:
   - side 0 chunk: bytes `0..255` of each 512-byte block
   - side 1 chunk: bytes `256..511` of each 512-byte block
3. Decode the side stream as MFM-like cells:
   - bits are read little-bit-order from each encoded byte
   - data phase observed for this image: `6`
   - data bits are the odd cells: `phase + j * 2 + 1`
4. The Centurion sector payload begins at decoded byte offset `75` within each decoded side/track stream.
5. Extract `20 * 400` bytes per track side.

The current `roms/cops.img` was produced from **side 0 only** so it can be mounted with biscvit's current single-head boot geometry:

```text
77 tracks * 20 sectors/track * 400 bytes/sector = 616000 bytes
```

## Conversion script

The extractor now lives at `scripts/extract_hfe_sectors.py`:

```sh
scripts/extract_hfe_sectors.py ../CenturionComputer/Drives/Floppy/FluxReading/CentOpSys.hfe roms/cops.img --side 0
```

It decodes each side stream as above, then extracts individual 400-byte sector payloads.  On normally formatted tracks the sector payload starts immediately after an 8-byte per-sector header following the observed `FF` gap.  The resulting side-0 image size is:

```text
77 tracks * 20 sectors/track * 400 bytes/sector = 616000 bytes
```

For a two-head track/head/sector ordered image:

```sh
scripts/extract_hfe_sectors.py ../CenturionComputer/Drives/Floppy/FluxReading/CentOpSys.hfe /tmp/cops_2h.img --all-sides
```

Track 0 side 0 of `CentOpSys.hfe` is a special bootstrap track that does not show the normal per-sector `FF` gap pattern, so the script falls back to the earlier contiguous payload extraction at decoded offset `75` for that track side.

## Validation

After conversion, `roms/cops.img` contains recognizable Centurion/WIPL strings when masking the high bit:

```text
FDIPL
@LOAD
@SYS
@OSN
READY
MONITOR
```

Example check:

```sh
python3 - <<'PY'
from pathlib import Path
b = Path('roms/cops.img').read_bytes()
m = bytes([x & 0x7f for x in b])
for term in [b'FDIPL', b'@LOAD', b'@SYS', b'@OSN', b'READY', b'MONITOR']:
    print(term.decode(), m.find(term))
PY
```

Smoke boot:

```sh
FLOPPY=roms/cops.img ./scripts/boot.sh --run --max 120000
```

Current observed output:

```text
D=F0
AB 47 - INCORRECT DISK FORMAT

FDIPL 6.2
NAME=
DISK=
```

So the image is decoded well enough for the ROM/WIPL path to execute and for WIPL to find its prompt text and catalog strings, but the disk format check still fails. Next likely work:

- verify sector ordering and payload offset,
- understand the side/head ordering expected by WIPL,
- add two-head FFC/image support if `CentOpSys.hfe` needs side 1 during boot,
- compare WIPL's disk-code/format check against the bytes around the catalog and volume label.
