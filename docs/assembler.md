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

## MULU / DIVU
Per the [Centurion wiki](https://github.com/Nakazoto/CenturionComputer/wiki/Instructions)
`0x77` is MULU and `0x78` DIVU (not JSR).  Only the register-register form is emulated; the
operand byte is `src pair <<5 | dst pair <<1`.  The exact result layout is inferred, not verified
on hardware:

| Op | Effect |
| --- | --- |
| `mulu(src, dst)` | `dst:dst+1` (32-bit) = `src * dst`; `dst` = high word, `dst+1` = low word |
| `divu(src, dst)` | dividend = `dst:dst+1`, divisor = `src`; `dst` = remainder, `dst+1` = quotient (low 16 bits); carry set if remainder is 0; divide by zero leaves registers alone and clears carry |

"Adjacent" pairs are `A:B`, `B:X`, `X:Y`, ... (so `B` pairs with `X`/RT).

## Not done yet
A text-source assembler using the native syntax (`LDAB/`, `LDA=`, `STA+`...), macros for
`if/else/loop`, jump-table helpers, and the odd-nibble memory forms of `5x`/`7x` ops.
