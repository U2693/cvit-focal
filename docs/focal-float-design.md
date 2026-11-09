# CPU6 FOCAL floating-point work

Status: **experimental; not yet used by FOCAL**. FOCAL still evaluates signed
16-bit integers. `scripts/cpu6_float.py` provides the first independently
testable CPU6 primitive (`fp_from_i16`), and `scripts/test_cpu6_float.py` runs
it on the emulated CPU6 against an exact host-side encoding oracle.

## Representation

Follow FOCAL/Nova's packed DG single format: big-endian 32-bit word, sign bit,
7-bit excess-64 hexadecimal exponent, 24-bit fraction, canonical zero all
zero. A nonzero value is `(-1)^sign * fraction / 2^24 * 16^(exp-64)`, with a
nonzero high hexadecimal fraction digit. This is a compatibility target, not
an assertion that Centurion hardware used this format. The Nova reference is
`../dusky-petrel/sd/focal.asm` and its `docs/focal.md`.

The first primitive accepts a signed integer in AX and returns the packed
value in AX:BX, clobbering only those registers, flags, and declared workspace.
All signed 16-bit integers are exactly representable. Its scratch area is
non-reentrant. Routines that call one another must avoid keeping live state in
that workspace or use stack frames; CPU6 RT is the JSR link register.

## Remaining work

1. Specify rounding, zero, underflow, overflow and division-by-zero behavior
   against Nova, including guard digits. Add a numerical test oracle and cases
   independently checked on SIMH, not merely self-consistent encode/decode.
2. Implement and test unpack/normalize/pack, comparison, add/subtract,
   multiply/divide, and float-to-integer CPU6 routines. Test normal and extreme
   exponents, signs, cancellation, rounding boundaries and error recovery.
3. Plan the expanded FOCAL memory map and stack before replacing the value
   representation: expressions, variables, FOR frames, ASK and TYPE all need
   conversion; line keys, addresses and indexes remain integers.
4. Add decimal parsing and formatting, including exponent notation and `%w.d`;
   then run common sessions against both Nova on SIMH and CPU6. Keep separate
   expectations where semantics intentionally differ.
5. Add functions and arrays only once the arithmetic and storage foundations
   are verified. Preserve LOAD/SAVE and existing integer-compatible sessions.

Use `nix develop -c python3 -m unittest discover -s scripts -p test_cpu6_float.py`
for the current primitive tests.
