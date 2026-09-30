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

## One-off conversion script

```python
from pathlib import Path
import struct

src = Path('../CenturionComputer/Drives/Floppy/FluxReading/CentOpSys.hfe')
dst = Path('roms/cops.img')
h = src.read_bytes()
assert h[:8] == b'HXCPICFE'

tracks = h[9]
sides = h[10]
track_table = struct.unpack_from('<H', h, 18)[0] * 512
sector_size = 400
sectors_per_track = 20
payload_offset = 75

def decode_track_side(track, side):
    off_blocks, length = struct.unpack_from('<HH', h, track_table + track * 4)
    raw = h[off_blocks * 512:off_blocks * 512 + length]

    # HFE alternates side data in 256-byte chunks.
    sidebytes = b''.join(
        raw[i + side * 256:i + (side + 1) * 256]
        for i in range(0, len(raw), 512)
    )

    bits = [(byte >> bit) & 1 for byte in sidebytes for bit in range(8)]
    out = bytearray()
    for k in range(6, len(bits) - 16, 16):
        value = 0
        for j in range(8):
            value = (value << 1) | bits[k + j * 2 + 1]
        out.append(value)
    return bytes(out)

# Side 0 only for current biscvit single-head geometry.
image = bytearray()
for track in range(tracks):
    decoded = decode_track_side(track, 0)
    payload = decoded[payload_offset:payload_offset + sectors_per_track * sector_size]
    image.extend(payload.ljust(sectors_per_track * sector_size, b'\x00'))

dst.write_bytes(image)
print(f'wrote {dst}: {len(image)} bytes')
```

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
