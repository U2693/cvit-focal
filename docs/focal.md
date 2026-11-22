# FOCAL on cvit

`RUN FOCAL` starts a small FOCAL-69-flavoured interpreter (`SYSTEM/FOCAL`, about 2.5 KB,
source in `scripts/focal.py`).  Numbers are **16-bit signed integers**.  `QUIT` returns to
the cvit `]` prompt.

```text
]RUN FOCAL

CVIT FOCAL V0.1
*1.1 ASK "N? ",N
*1.2 FOR I=1,N; TYPE I*I,!
*1.3 TYPE "DONE",!
*GO
N? 5
1
4
...
```

## Lines and modes
- A line starting with a number `G.SS` is stored (`1.1` means `1.10`; keys 0.01-99.99, 128 lines of up to 60
  characters); a number alone deletes the line.  Anything else runs immediately.
- Several commands per line are separated by `;`.  Commands are matched by their first letter,
  and the rest of the word is ignored (`T`, `TYPE`, `TYPEOUT`).

## Commands
| Command | Meaning |
| --- | --- |
| `TYPE items` | Items separated by `,`: `"text"`, `!` (CR LF), `#` (CR), or an expression (printed in decimal). `%` format specs are skipped. |
| `SET v=expr` | Assign a variable (`A`-`Z`, single letters, initially 0) |
| `ASK ["prompt",] v` | Read an expression from the terminal (prompt `:` if no string) |
| `IF (expr) a,b,c` | Go to line `a`, `b` or `c` for negative, zero, positive; a missing/blank target continues |
| `GO [n]` | Jump to line `n` (next existing line at or after it); `GO` alone runs from the first line |
| `DO n` | Call line `n.SS`, or every line of group `n` (`DO 2`); `RETURN` ends the call |
| `FOR v=a[,step],end; commands` | Loop; the commands are the rest of the line.  Negative steps count down |
| `RETURN` | End a `DO` (or the program) |
| `WRITE [group or line]` | List the whole program, one group, or one exact line in line order |
| `LOAD file` | Load numbered source lines from a cvit text member, replacing the current program |
| `SAVE file` | Save the current numbered program to a cvit text member, creating it if needed |
| `ERASE` | Delete all lines |
| `COMMENT text` | Ignore the rest of the line |
| `QUIT` | Leave FOCAL |

## Dot commands (prompt only)

System escapes at the `*` prompt, in the cvit house style of COMMAND `.STA`/`.CED`:

| Command | Meaning |
| --- | --- |
| `.HELP` | List the dot commands and the FOCAL command words |
| `.SAVE name` | Save the current program to a cvit text member (same service as `SAVE`) |
| `.LOAD name` | Load a program member, replacing the current program (same service as `LOAD`) |
| `.RUN name` | Load a program member and run it (load and go); the current program is erased first |

Easter egg: `!name` at the prompt runs a binary cvit member (SVC $56), returning to `*` when it returns. Not listed in `.HELP`.

## Expressions
+ - * / with the usual precedence, right-associative ^, unary -, parentheses, numbers and variables.
Values are decimal floating point (Stage 3a): 7-digit mantissa, exponent -38..38, held in 4 bytes per
variable.  Literals may carry a fraction and an E exponent (2.5, 0.001, 6.02E2).  ^ takes an
integer-valued exponent (truncated, clamped to +-32767); negative exponents reciprocate, and 0^0 is 1.
TYPE prints 6 significant digits, fixed notation for exponents -3..6 with trailing zeros trimmed,
Nova-style 0.ddddddE+XX outside that range.  FOR steps may be fractional.  Errors: ?SYNTAX,
?DIV0 (division by zero), ?OVF (exponent overflow), ?FULL (all 128 line slots used).  An error
aborts the current run and returns to the * prompt.  The format and semantics are specified in
docs/focal-float-design.md; the library is differentially tested by scripts/test_fp_stage3.py.

## Variables
A variable is a single letter (not F) with an optional subscript: X, X(3), X(I+1).  The
subscript is any expression, truncated toward zero to an integer, and may be negative.  The
default subscript is 0, so X and X(0) are the same variable.  Variables are created as 0 on
first reference and live in a pool holding 60 distinct (letter, subscript) pairs; creating
a 61st gives ?VAR.  Variables survive ERASE (which clears only the program); they are
cleared at cold start and by .run.

## Functions
FABS(x) absolute value, FSGN(x) sign (-1, 0 or 1), FITR(x) integer part (truncation toward
zero, full range, not clamped to 16 bits), FSQT(x) square root by Newton iteration from a
halved-exponent guess.  As on the Nova, a function name is F plus a two-letter key (AB, SG,
IT, SQ); the full names are the usual spellings and any extra letters after the key are
skipped.  FSQT of a negative number and an unknown function both give ?FUN.  F is reserved
and cannot be used as a variable.

## Not (yet) in this FOCAL
FSIN and other functions, MODIFY,
`LIBRARY`, `TYPE $`, `%` output formatting, and line-number-less `IF` forms.

## Implementation notes
- Register use: `Z` = text pointer, `A`/`B` = scratch and expression results, `Y` = scratch/`MULU` operand.
  The link register `X`/RT is never used for data because `MULU`/`DIVU` are done on `A:B`.
- Values and `FOR`/`DO` frames are on the hardware stack; the program is stored as 64-byte slots at
  `0x8000-0x9FFF`, so there is no memory shifting; "next line" is a scan for the smallest greater key.
- Memory: code at 0x5000 (about 8.5 KB with the FP library); line buffers at 0x7C00/0x7C60; variables 0x7D00 (4 bytes each); interpreter state and FP workspace at 0x7D80.
- Tests: `python3 scripts/mk_test_os.py && python3 scripts/test_focal.py` inside `nix develop`. `testdata/focal-common.session` exercises a common subset inspired by the Nova suite, with biscvit-specific integer output in `testdata/focal-common.expected`. It is not a SIMH parity test.
