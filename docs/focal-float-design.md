# CPU6 FOCAL floating point

Status: **Stage 3a-i complete; not yet wired into FOCAL**. The decimal FP
library in  is implemented and differentially tested
against a Python model by  (arithmetic, compare,
conversions, decimal parse and print). Wiring it into the FOCAL evaluator is
Stage 3a-ii.

## Representation

The internal format is decimal, not the DG binary format an earlier
experiment used. Nothing outside the evaluator ever sees raw float bits
(LOCAL stores program text), so the format that is cheap on a CPU6 wins.
Four bytes, big-endian: byte 0 is sign (0x80) ORed with (exp10 + 64);
bytes 1-3 hold a 7-digit mantissa M (1000000..9999999) as a binary integer.
Value = M x 10^(exp10 - 6). Zero is four zero bytes. exp10 range is -38..38;
beyond that an op sets fp_ovf (positive overflow) or flushes to zero
(underflow). Division by zero sets fp_divz.

Values travel in A:B; the second operand sits in memory at fp_fop. Routines
clobber A, B, Y, Z and the fp_ workspace, never X (RT is the JSR link
register; writing it destroys the return address).

Add/subtract align by shifting the smaller mantissa right (truncating), or
the larger one left when its mantissa has a spare digit; this matches the
test model exactly, including last-digit differences from exact arithmetic
after catastrophic cancellation. Print rounds to 6 significant digits
(half-up on the 7th), fixed notation for -3 <= exp10 <= 6 with trailing
zeros trimmed, Nova-style scientific 0.ddddddE+XX outside that range.
Parse accepts up to 7 significant digits, a fraction, and E notation. fp_trunc (the FITR function) drops fractional digits by dividing the mantissa by 10^(6-exp10) and renormalising; full range, toward zero.

## Tests



## Remaining work

1. Stage 3a-ii: wire FP into scripts/focal.py (variables become 4 bytes,
   SET/TYPE/ASK/IF/FOR on floats, ^ with integer-valued exponents,
   fp_ovf/fp_divz/fp_perr mapped onto FOCAL error reports).
2. Stage 3b: FABS FSGN FITR FSQT. Stage 3c: subscripted variables.
   Stage 3d: LOCAL WRITE/READ.
3. Percent formats and TYPE $ come with or after 3a-ii.
