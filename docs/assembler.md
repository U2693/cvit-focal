# cpu6asm

`scripts/cpu6asm.py` is a small Python-embedded CPU6 assembler used to build the
cvit kernel, COMMAND and programs.  Run its tests with
`python3 scripts/test_cpu6asm.py`.

```python
from cpu6asm import Asm
a = Asm(0x5000).vars_at(0x2400)
a.var("COUNT")                       # 2-byte scratch word at 0x2400
a.lda_label("msg").xaz()             # Z = &msg
a.ldbb_i(2).svc(0x40)                # cvit puts
a.cmp_al(0x0D).beq("done")           # compare AL with CR (clobbers BL)
a.label("done").rsr()
a.label("msg").asciz("HELLO\r\n")
code = a.bytes()
print(a.listing())
```

## Features
- **Symbols.** Labels, `equ(name, value)` and `var(name, size)` (after `vars_at`).
  Any 16-bit operand (`lda_i`, `ldb_i`, `lda_d`, `sta_d`, `jmp_abs`, `dw`, ...) accepts an
  int or a symbol name.
- **Automatic branch relaxation.** `bz`/`bnz`/`bl`/`bnc`/`bm`/`bp`/`bgz`/`ble`, `jmp` and `jsr`
  use the short relative form when the target is within -128..127 and otherwise become an
  inverted branch over an absolute `JMP` (or an absolute `JMP`/`JSR`).  Layout is iterated until stable.
- **Compare helpers.** `cmp_al(imm)` (`LDBB`+`SABB`) and `cmp_ax(imm)` (`LDB`+`SAB`) set flags
  as `AL/AX - imm` (they clobber `BL`/`BX`).  Aliases: `beq`, `bne`, `bhs` (carry = A >= imm),
  `blo`, `bgt`.
- **Register-generic ops.** `xfr`, `xfrb`, `inr`/`dcr` (count 1-16), `inrb`/`dcrb`, `mulu`, `divu`,
  `push`/`pop` (byte registers).  Registers are `A B X Y Z S C P` (biscvit: AX BX RT DX EX SP GX HX)
  and byte registers `AH AL BH BL ...`.
- **Indexed addressing.** `ldab_x(reg, mode, disp, indirect)` and friends
  (`lda_x`, `stab_x`, `sta_x`, `ldbb_x`, `ldb_x`, `stbb_x`, `stb_x`, `jmp_x`, `jsr_x`), `mode` = `''`, `'+'`, `'-'`.
- **Data.** `db`, `dw`, `ascii`, `asciz`, `ds`, `align`.
- **Debugging.** `listing()` (address, bytes, labels, branch targets, `(long)` for relaxed branches),
  `symbols()`, and clear `AsmError`s for undefined/duplicate symbols.

## MUL / DIV
Semantics come from the Centurion project's `optest07.asm` ("Test MUL" / "Test DIV"), verified by the
emulator tests.  Operand byte: high nibble = src, low nibble = dst, each `pair*2` with bit 0 = "memory form".

| Assembler | Form | Meaning |
| --- | --- | --- |
| `mulu(s, d)` / `divu(s, d)` | reg,reg | `d * s` / `d / s` |
| `mul_imm(imm, s[, d])` / `div_imm(...)` | `MUL= imm,s[,d]` | `imm * s` / `s / imm` (word follows) |
| `mul_mem(addr, s[, d])` / `div_mem(...)` | `MUL/ addr,s[,d]` | `[addr] * s` / `s / [addr]` |
| `mul_idx(i, disp, d)` / `div_idx(...)` | `MUL- i,disp,d` | `[i+disp] * d` / `d / [i+disp]` (word displacement) |

Results go to `d`.  MUL: high word in `d` and low word in the next pair when `d` is A/X/Z/C (even pair
index: A:B, X:Y, Z:S, C:P); only the low word in `d` when `d` is B/Y/S/P.  DIV: remainder in `d` and
quotient in the next pair (even `d`), or quotient only in `d` (odd `d`).  The dividend is 16-bit.  L is set
when the remainder is zero (from the older wiki page).  Divide by zero leaves the registers alone
(unverified).  Example: `lda_i(13).ldb_i(6).divu("B","A")` gives A=1, B=2.

## Text export

`a.asm(title=None)` renders the program back as native-style text assembly:
labels and `EQU` symbols kept, data as `DB`/`DW`/`DS`, relaxed branches and
page-safe pads annotated in comments.  It walks the item stream and decodes
each instruction item, so what you read is what `bytes()` emits.  Export only
-- cpu6asm does not (yet) assemble text input.

## Not done yet
A text-source assembler using the native syntax (`LDAB/`, `LDA=`, `STA+`...), macros for
`if/else/loop`, jump-table helpers, and the odd-nibble memory forms of `5x`/`7x` ops.
