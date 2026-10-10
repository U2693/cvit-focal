# BIGNUM (opcode 0x46) notes

Reference notes on the Centurion `0x46` "bignum" instruction family, gathered from an LLVM backend for the CPU6
(`ddemarco5/llvm-project-centurion`, branch `23.x-cpu6`, test `llvm/test/CodeGen/CPU6/bignum.ll`, about 1,260 lines)
and from Meisaka's emulator source.  The backend notes say its semantics were "run on the machine" (4- and 8-byte
operands, negative values, source and destination at one address), so treat them as the best evidence available.
I only read the test file's comments and CHECK lines; nothing here has been re-verified in biscvit yet.

## Selectors

`46 ssssmmnn ...`: the high nibble `s` selects the operation; `m`/`n` are the operand addressing modes.

| s | LLVM mnemonic | Meisaka name | Meaning |
| --- | --- | --- | --- |
| 0 | `BNA` | `A` / ADD | Dest := Dest + Src |
| 1 | `BNS` | `S` / SUB | Dest := Dest - Src |
| 2 | `BNC` | `C` / CMP | flags of Dest - Src (no result) |
| 3 | `ZAD` | `ZAD` / MOV | Dest := Src |
| 4 | `ZSU` | `ZSU` / NEG | Dest := -Src |
| 5 | `M` | `M` / SMUL | Dest := Dest * Src |
| 6 | `D` | `D` / DIV | Dest := Dest / Src (signed) |
| 7 | `DRM` | `DRM` / DIVMOD | quotient -> Dest, remainder -> the address in A |
| 8 | | `CTB` / TOBIN | base string -> big number (biscvit implements this) |
| 9 | | `CFB` / FMBIN | big number -> base string (biscvit implements this) |

(The selector numbers follow Meisaka's table order `A S C ZAD ZSU M D DRM CTB CFB`; the LLVM mnemonics are the
backend's names for the same operations.)

## Operands

- **Two length operands, each length-1**: `3` = 4 bytes (i32), `7` = 8 bytes (i64), `15` = 16 bytes (i128).
  Syntax: `BNA 15,15,(src128),(dst128)`.  Operand order in the assembly is (Src, Dest) for `ZAD/BNA/BNS/ZSU/M/D`.
- **Forms**: absolute `(label)`; register-register (`RR`, operands are pointer registers); indexed `(S),16`
  (register plus displacement) which allows a stack slot to be used directly, e.g. `BNA 15,15,(S),0,(S),16`; and a
  **literal source** (an inline byte).  The 8-bit displacement is signed (-128..127); further slots need the 16-bit
  displacement form or an `ADD` plus a register.
- **Literal source**: the inline byte is sign-extended and added at the low byte, so the constant must fit in -128..127
  (255 is -1, not 255).  Larger constants need the carry chain.

## Behaviour worth remembering

- **Byte-serial**: operations are performed byte by byte, so a source and destination that overlap by a partial amount
  (for example two bytes apart) do not behave like load-then-store.  The backend refuses to fold those.  Same address for
  source and destination (`M 3,3,(x),(x)`) is fine.
- **BNC flags**: `==`/`!=` read V (zero); unsigned order reads Link (set = no borrow).  Dest is the left operand of `>=` and
  `<`, and the right operand of `>` and `<=`; `a <= b` is `b >= a` so operands swap.  There is **no signed compare**: signed
  order stays a word compare.
- **`DRM`**: the quotient goes to Dest, the remainder to the address held in register `A`, so `A` must be set last (after the
  dividend is copied to the quotient temporary).  Writing quotient and remainder to the same address gave a wrong remainder
  (+1 for -22 % 7), so the backend always sends the quotient to a temporary; the remainder over the divisor is right for
  every sign.
- **`BNS` with Dest as the subtrahend** cannot run in place: copy the minuend to a slot, subtract in the slot, copy back.
- A "multiply of two registers" is `M` (no `__multi3` call); `ZAD 3,3,A,Y` followed by `M 3,3,B,Y` is the register form.

## The stack-slot lowering (why it matters)

The backend places bignum temporaries in single-use frame slots and addresses them directly through `S`, so the whole
"create numbers on the stack, take pointers, add, store" sequence folds into one instruction:

```llvm
%d = alloca i128, align 1
%s = alloca i128, align 1
%a = load i128, ptr %d, align 1
%b = load i128, ptr %s, align 1
%c = add i128 %a, %b
store i128 %c, ptr %d, align 1
```
becomes
```
BNA 15,15,(S),0,(S),16
ADD S,S,32
RSR
```
Program size and register pressure are minimal (the author has not measured microstep cost).  Objects that are reused by
several operations, or whose slot is outside the signed-byte displacement, stay register-based.  Place byte arrays nearest
`S` because a byte displacement has no fallback.

## Relevance to biscvit

- `Program.cs` `BigNum()` implements only the base-conversion selectors (`8`, `9`) and a few basics; the arithmetic selectors
  `0-7` above are not modelled to this level, and neither the literal-source form nor the exact flag behaviour of `BNC`.
- FOCAL (`scripts/focal.py`) uses 16-bit `MUL`/`DIV` only; a 128-bit or 32-bit path could use `BNA`/`M`/`D` once implemented.
- Possible work: implement selectors 0-7 with all operand forms; turn the `bignum.ll` CHECK lines into assembled run-time
  tests (`ZAD`, `BNA`, `BNS`, `BNC` + branch, `M`, `D`, `DRM`); add `bna/bns/bnc/zad/zsu/m/d/drm` helpers to `cpu6asm`;
  confirm the exact byte encodings of the operand forms (the wiki's `47/67` memory-op page uses the same `ssssmmnn` idea).

## Sources
- https://github.com/ddemarco5/llvm-project-centurion/blob/23.x-cpu6/llvm/test/CodeGen/CPU6/bignum.ll
- Meisaka's emulator source `Emulators/Meisaka/Emu 0.22/src/cen.ts` (CenRE license): `BIG.` table at opcode `0x46`
- Centurion wiki: Instructions, `Inst_Old` (the `46` chart)
