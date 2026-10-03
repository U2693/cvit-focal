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
   - data bits are the odd cells: `phase + j * 2 + 1`
   - CentOpSys track 0 side 0 decodes with phase `6`
   - normal data sectors can land on either phase `6` or phase `14`; the converter scores both per sector and chooses the less nibble-shifted-looking payload
4. The Centurion sector payload begins at decoded byte offset `75` within each decoded side/track stream.
5. Extract `20 * 400` bytes per track side.

The current `disks/cops.img` was produced from **side 0 only** so it can be mounted with biscvit's current single-head boot geometry:

```text
77 tracks * 20 sectors/track * 400 bytes/sector = 616000 bytes
```

## Conversion script

The HFE-to-Disk-6 converter now lives at `scripts/hfe_to_disk6.py`:

```sh
scripts/hfe_to_disk6.py ../CenturionComputer/Drives/Floppy/FluxReading/CentOpSys.hfe disks/cops.img --side 0
```

It decodes each side stream as above, extracts individual 400-byte sector payloads, and applies the current CentOpSys Disk-6 boot/volume/catalog reconstruction.  On normally formatted tracks the converter now uses the fixed nominal sector starts.  Earlier FF-gap scanning was useful for discovery but is unsafe for extraction because real payloads can contain long `FF` runs that look like sector gaps.  The resulting side-0 image size is:

```text
77 tracks * 20 sectors/track * 400 bytes/sector = 616000 bytes
```

For a two-head track/head/sector ordered image:

```sh
scripts/hfe_to_disk6.py ../CenturionComputer/Drives/Floppy/FluxReading/CentOpSys.hfe /tmp/cops_2h.img --all-sides
```

Track 0 side 0 of `CentOpSys.hfe` is a special bootstrap/volume track that does not show the normal per-sector `FF` gap pattern.  Current handling is explicit:

- logical sectors `0..9` come from the contiguous IPL area at decoded offset `75`,
- logical sector `14` is synthesized as a Disk-6 volume record whose key/offset decodes to directory sector `0x0010`,
- logical sector `16` receives the catalog record found at decoded offset `5312` (`GOTEK`, `@SYS`, `@OSN`, `@LOAD`, etc.).

This matches the FDIPL access pattern observed via FFC tracing: sector `0x000E` is checked for the Disk-6 flag, then sector `0x0010` is read as the volume directory.

## Validation

After conversion, `disks/cops.img` contains recognizable Centurion/WIPL strings when masking the high bit:

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
b = Path('disks/cops.img').read_bytes()
m = bytes([x & 0x7f for x in b])
for term in [b'FDIPL', b'@LOAD', b'@SYS', b'@OSN', b'READY', b'MONITOR']:
    print(term.decode(), m.find(term))
PY
```

Smoke boot should use normal floppy track/sector FFC addressing, not `FFC_LINEAR_EXPERIMENTAL=1`:

```sh
scripts/hfe_to_disk6.py ../CenturionComputer/Drives/Floppy/FluxReading/CentOpSys.hfe /tmp/cops_side0.img --side 0
FLOPPY=/tmp/cops_side0.img FLOPPY_HEADS=1 ./scripts/boot.sh --run --max 150000 --floppy-trace
```

Important: `FFC_LINEAR_EXPERIMENTAL=1` / `--ffc-linear-experimental` treats the FFC track and sector bytes as a 16-bit linear block address. That is useful only as an experiment and is not the floppy protocol. FDIPL's read of Disk-6 sector `0x0020`, for example, appears on the FFC as track `1`, sector `12` (`0x20 / 20`, `0x20 % 20`), not as a Hawk-style linear address `0x0020`.

Current observed output no longer reports `AB 47`:

```text
D=F0

FDIPL 6.2
NAME=
DISK=
```

Important trace points:

```text
FFC READ track=00 sector=14 disk6=$000E ... raw_offset=5600 first16=78 C5 00 00 EF 2C E4 54 FF FF ...
FFC READ track=00 sector=16 disk6=$0010 ... raw_offset=6400 first16=C7 CF D4 C5 CB A0 A0 A0 A0 A0 ...
```

So the image now passes the Disk-6 format check and reaches the FDIPL prompts.

The Disk-6 key bytes in the synthesized volume record are `E4 54`; applying the decode used by Meisaka's disk viewer gives decimal disk code `100`.  This code passes the AB48 check:

```sh
BOOT_KEYS='F0\r\r100\r' FLOPPY=/tmp/cops_side0.img FLOPPY_HEADS=1 ./scripts/boot.sh --run --max 500000 --floppy-trace
```

A bad code such as `00` produces:

```text
AB 48 - INCORRECT DISK CODE
```

After accepted `CODE=100`, FDIPL performs additional reads. With floppy CHS addressing, the next notable access is the Disk-6 UAL base `0x0020` as FFC track `1`, sector `12`.  This now decodes as a plausible UAL sector when the normal-track per-sector phase heuristic chooses phase `14` for that sector:

```text
FFC READ track=01 sector=12 disk6=$0020 ... first16=00 0F 80 00 04 00 00 00 00 FF FF FF ...
```

FDIPL then follows the `@LOAD` UAL and reads sectors `$02C4`, `$02C5`, `$02C6`, etc.  Its object loader uses CPU6 `67 4A 86` (`memcpy AL+1,[Z],[Y]`) to copy data records before advancing its own pointers; biscvit now implements that form.  Current traces progress through many more `@LOAD` sectors (at least into `$02E8`), but the loaded code still does not reach a visible prompt/output.

Next likely work:

- trace execution after the `@LOAD` sector reads and identify where the loaded program stalls/halts,
- compare FDIPL's directory/UAL walk with Meisaka's `DiskVol` interpretation,
- keep floppy FFC addressing as CHS; reserve linear addressing for a separate hard-disk/Hawk path if needed.
