# Notes from CENTOS_12.IMG and the Centurion references

## Where the semantics came from
- Wiki *Instructions* page: opcode map (`0x77` MUL, `0x78` DIV, `0x79` JSR direct, ...).
- `CenturionComputer/Software/New Software/Bible/optest07.asm`: per-instruction test listing with
  commented expected results; this is the authority for `MUL`/`DIV` (see `assembler.md`).
  My first guess (32-bit dividend in `dst:dst+1`) was wrong: the dividend is 16-bit and the quotient goes
  to the *next* register only when `dst` is A/X/Z/C.

## Real volume layout (CENTOS_12.IMG)
- Volume label `SOFTERM`, UAL base sector `0x30`, catalog at sector `0x10`.
- Catalog files: system files `@SLOD0`, `@SDIR0`, `@SUAL0`, `@SFAL0`, `@SYS`, `@LOAD`, `@OSN`, `@SCR0/A/B/C/E`
  and user files such as `HELP`, `SORT10`-`SORT40`, `PC`, `GL`, `GLMENU`, `ZFDUMP`.  Attribute bytes `0x10`-`0x15`.
- File maps list data sectors 16 apart (`0x500`, `0x510`, `0x520`, ...): files are striped one sector per track.
- `mkhawk.py` builds a single `SYSTEM` library at sector `0x20`, which matches the boot path but not the real
  catalog structure.

## Booting the real image
Resolved by reading Draco's CenturionJS (`src/cards/CPU6/CPU6.ts`) and the wiki's `OpC_20-2F` / `OpC_40-4F`:
- **`0x2E` is not LDM.**  It is the PageTable (MMU) family: `2E ssssmmnn` (selectors WPF, RPF, WPF1, RPF1,
  WPFH, RPFH; operand 1 = literal byte "map | index<<3", operand 2 = address).  biscvit's old `2E` decoding
  (LDM) made the `78`s at `CFD4` look like instructions; they are really address bytes.  Now implemented
  (page tables stored, no address translation yet).
- **`0x47`/`0x67` memcpy/memcmp/memset** are decoded per the wiki mode bits (direct / indexed / register /
  inline literal) instead of the old special cases; the loader's `67 4A 86` still works.
- The "four-byte literal" experiment below was therefore a red herring.

## MMU and physical memory (implemented)
Model taken from CenturionJS (`CPU6Card.ts`) and the wiki:
- 18-bit physical space; 2 KB pages; 8 maps x 32 entries (`2E` WPF/RPF ops), 7 bits of physical page per entry.
- Physical = `entry<<11 | addr&0x7FF`.  Default tables: identity for pages 0-29, page 30 -> `0x7E`, 31 -> `0x7F`, so logical
  `F000-FFFF` is physical `0x3F000-0x3FFFF`, the I/O + boot-ROM window.  Map 0 is active (maps are switched by JSYS/RSYS, not
  modelled yet).
- RAM is `[0, --ram-kb)` (default 64 KB); anything else reads `0xFF` and ignores writes (CenturionJS does the same), so RAM-size
  probing works.  RPF reads return the entry with bit 7 from `MemStatus` (always 0 for now).
- The register file (low addresses `0x00-0xFF`) is physical and bypasses the page tables.

## Opcode corrections from Meisaka's emulator source (`Emulators/Meisaka/Emu 0.22/src/cen.ts`)
The CenRE-licensed source (read only, nothing copied) has the authoritative opcode/mode table.  What it fixed in biscvit:
- **RC-type word ops with an odd register nibble operate on memory** (`INR/DCR/CLR/IVR/SRR/SLR/RRR/RLR`): `30 1c aaaa` is
  `INR [aaaa]`, `30 rc dddd` is `INR [reg+dddd]`.  The CentOS probe loop's `30 10 D4 D4` is `INR [D4D4]`, the page counter
  (it counts `1E`..`7D`).  I had decoded it as `INR A` followed by a bogus `LDB`, which is why nothing ever changed `D4D4`.
- **`CLR r,n` loads the constant n** (0-15), e.g. `32 CD` = `CLR C,13`.
- **Low nibble 6/7 on `80-FF` are not addressing modes**: `86 DPE`, `96 SOP`, `A6 SEP` (parity, no-ops here), `B6 ECK`, `C6 DCK`,
  `D6 STR`, `D7 SAR`, `E6 LAR`, `F6 LIO/SIO`, `F7 MVL`; `87 97 A7 B7 C7 E7` are illegal.
  `MVL` is implemented as "copy A+1 bytes from [B] to [Y]; B,Y advance; A=FFFF" (end state inferred).  `ECK/DCK` drive a clock tick
  (`BCK` branches on it).  `STR` (`D6`) follows the wiki's four forms.
- **`F6` XIO is `jk dd`**: `EA = (base + dd) | 0x3F000` (always the I/O window), `j` = data register, `k&14` = base register,
  `k&1` = store, a high-byte flag selects the byte form.  This replaced the old Z-only special cases.
- **SVC (`66 nn`) / RSV (`0F`)** follow CenturionJS's JSYS/RSYS: push map, IPL, X, argument; X<-PC; map 0; PC=`0100`; RSV pops them
  (and so can switch IPL/map: the OS builds RSV frames by hand to dispatch tasks).  The cvit `SVC $40` convention is kept.
- `EPE` (`76`) is a no-op.

## Where CentOS stops now
`scripts/bis --hawk CENTOS_12.IMG --ram-kb 128` (boot keys `H0`): the memory probe finishes, the OS sizes memory, sets up page
tables and level-15 state and enters the resident kernel at `8000-80FF` (about 36,000 instructions in).  It then does
`JSR *A` through a vector at `A1FA` that is still zero (the table around `A1F0` is an empty list), so execution falls into page 0.
The kernel's message table (`OPSYS ABORTED`, `ATTEMPTING AUTO-RECOVERY`, `MEMORY LOCK`, ...) is at `8130`+, so this is probably
an abort path.  Next steps: find what should have filled the `A1FA` table (a disk read via the Hawk, a DMA, or an interrupt
handler), and how RSV-based dispatch is meant to run the first task.
Tools: `--trace`, `--regs`, `--dump addr len`, `--ram-kb n`.  (Don't trace 30M steps: that is a few GB.)

## Earlier experiment (superseded): four-byte literal for DIV=
Making the literal form of `0x78` consume four operand bytes (instead of the two that optest07 suggests)
moves the halt from `CFE9` to `CFF3`: the third site in that block starts with `00 D4 CD 90 78 05`, i.e.
a `HLT` where the first two sites have `78`.  The same block layout (`[op] D4 xx yy zz ww 55 26 ...`) repeats three
times, so either (a) those opcode bytes are patched at run time (self-modifying code) by something the
emulator does not model, or (b) execution reached this block through a path that real hardware does not take.
Reverting `0x78` to the old "JSR AX" behaviour instead wanders into `E828` (a `HLT`), so neither reading
boots.  Not resolved; the experiment was reverted (the optest07 two-byte literal stays).  Things to try next:
trace what writes to `CFD0-CFFF` before the block runs, and check the `D7` (interlevel) and `F7` (`STB` via `P`)
instructions that run just before it.
