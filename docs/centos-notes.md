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
`scripts/bis --hawk CENTOS_12.IMG` (boot keys `H0`) now gets past the first `DIV` it hits at `CFD4`
(`78 D4 CD D0 ...`, `DIV= imm,C,X` in the literal form).  It then halts at `CFE9` on a `HLT` that follows a
second `78 D4 CC D0` probe.  This region looks like a CPU-type or instruction probe (CPU5 vs CPU6), so the
open question is the encoded length of the literal form: with a 2-byte literal the bytes `01 00` that follow
the second probe execute as `NOP; HLT`; if the real instruction consumed four operand bytes, execution would
continue past them.  Tools: `--trace`, `--regs` and `--dump addr len` on the biscvit command line.
