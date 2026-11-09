"""CPU6 floating-point primitives for future FOCAL integration.

The packed format is DG single precision: sign, excess-64 base-16 exponent,
24-bit hex-normalized fraction. Values are stored most-significant byte first.
These routines are experimental and are not yet wired into FOCAL.
"""


def declare_float_workspace(a):
    """Reserve the non-reentrant workspace in the assembler's variable area."""
    a.var("fp_mag")
    a.var("fp_exp")
    a.var("fp_sign")
    a.var("fp_out", 4)


def emit_float_routines(a):
    """Emit fp_from_i16: AX=signed integer; returns AX:BX=packed float.

    Clobbers AX, BX, flags and fp_* workspace. Preserves the other register
    pairs. Every 16-bit integer is exactly representable; zero is canonical.
    """
    a.label("fp_from_i16")
    a.sta_d("fp_mag").lda_i(0).sta_d("fp_sign")
    a.lda_d("fp_mag").bz("fp_i_zero").bm("fp_i_negative")
    a.jmp("fp_i_normalize")
    a.label("fp_i_negative")
    a.ldb_d("fp_mag").lda_i(0).sab().stb_d("fp_mag")
    a.lda_i(0x80).sta_d("fp_sign")
    a.label("fp_i_normalize")
    a.lda_i(68).sta_d("fp_exp")
    a.label("fp_i_loop")
    a.lda_d("fp_mag").cmp_ax(0x1000).bhs("fp_i_pack")
    a.sll_ax(4).sta_d("fp_mag")
    a.lda_d("fp_exp").ldb_i(0xFFFF).aab().stb_d("fp_exp")
    a.jmp("fp_i_loop")
    a.label("fp_i_pack")
    a.ldab_d("fp_exp+1").ldbb_d("fp_sign+1").orb_bl_al().stab_d("fp_out")
    a.ldab_d("fp_mag").stab_d("fp_out+1")
    a.ldab_d("fp_mag+1").stab_d("fp_out+2")
    a.ldab_i(0).stab_d("fp_out+3")
    a.lda_d("fp_out").ldb_d("fp_out+2").rsr()
    a.label("fp_i_zero")
    a.lda_i(0).ldb_i(0).rsr()
