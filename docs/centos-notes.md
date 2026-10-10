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

Status: `scripts/bis --hawk CENTOS_12.IMG` (boot keys `H0`) now runs the OS's early setup (page-table writes,
copying code stubs to `7800`/`7805`) and then loops in a memory-probe routine at `D030-D061` that uses the
MMU `2E` instructions and byte stores to find the end of RAM, so the next step is modelling page-table reads
(RPF "set top bit from MSR") and a larger, mapped memory.  Tools: `--trace`, `--regs`, `--dump addr len`.

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
