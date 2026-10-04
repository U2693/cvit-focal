def emit_hawk_read(a, label, sector, dst):
    a.label(label)
    a.lda_i(dst).dma_sad_a()
    a.lda_i(0xFE6F).dma_sct_a()      # -401 -> 400 bytes
    a.dma_sdv_0().dma_eab()
    a.lda_i(0xF140).xaz()            # Z = Hawk registers
    a.jsr_abs("hawk_ready")
    a.lda_i(sector).ldb_i(0x3FFF).nab().stb_z(1)   # F141/F142 = sector address
    a.ldab_i(2).stab_z(8)            # seek
    a.jsr_abs("hawk_ready")
    a.ldab_i(0).stab_z(8)            # read
    a.jsr_abs("hawk_busy")
    ok = f"{label}_ok"
    a.xfrb_au_al().bz(ok)            # AU = F144 status byte
    a.jmp_abs("hawk_error")
    a.label(ok)
    a.rsr()


def emit_hawk_waits(a):
    a.label("hawk_busy")
    a.ldab_z(4).srab().bl("hawk_busy")
    a.label("hawk_ready")
    a.lda_z(4).ldbb_i(0x30).andb_bl_al().sabb().bnz("hawk_ready").rsr()
    a.label("hawk_error")
    a.print("\r\nHAWK READ ERROR\r\n").hlt().jmp("hawk_error")
