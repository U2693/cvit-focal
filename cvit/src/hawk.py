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


def emit_hawk_write(a, label, sector, src):
    """Write one 400-byte Hawk sector from memory (command 1).

    Mirror of emit_hawk_read: same DMA setup, seek, then the write
    command; a nonzero F144 status byte goes to hawk_error.
    """
    a.label(label)
    a.lda_i(src).dma_sad_a()
    a.lda_i(0xFE6F).dma_sct_a()      # -401 -> 400 bytes
    a.dma_sdv_0().dma_eab()
    a.lda_i(0xF140).xaz()            # Z = Hawk registers
    a.jsr_abs("hawk_ready")
    a.lda_i(sector).ldb_i(0x3FFF).nab().stb_z(1)   # F141/F142 = sector address
    a.ldab_i(2).stab_z(8)            # seek
    a.jsr_abs("hawk_ready")
    a.ldab_i(0xFF).stab_z(3)         # write-protect mask: enable writes
    a.ldab_i(1).stab_z(8)            # write
    a.jsr_abs("hawk_busy")
    ok = f"{label}_ok"
    a.xfrb_au_al().bz(ok)            # AU = F144 status byte
    a.jmp_abs("hawk_error")
    a.label(ok)
    a.rsr()


HB_SECTOR_CELL = 0x2EF0  # scratch cell: saved CB sector (low-memory kernel page)


def _emit_hawk_block(a, label, cmd):
    """Kernel block vector body: transfer one 400-byte Hawk sector.

    BX points at a control block: +0 u16 sector, +2 u16 buffer address.
    AL returns the F144 status byte (0 = ok); the caller decides what an
    error means, so unlike emit_hawk_read this never halts. The sector is
    saved to a cell first because hawk_ready trashes BL, hence BX.
    """
    a.label(label)
    a.lda_bx(0).sta_d(HB_SECTOR_CELL)
    a.lda_bx(2).dma_sad_a()
    a.lda_i(0xFE6F).dma_sct_a()      # -401 -> 400 bytes
    a.dma_sdv_0().dma_eab()
    a.lda_i(0xF140).xaz()            # Z = Hawk registers
    a.jsr_abs("hawk_ready")
    a.lda_d(HB_SECTOR_CELL).ldb_i(0x3FFF).nab().stb_z(1)
    a.ldab_i(2).stab_z(8)            # seek
    a.jsr_abs("hawk_ready")
    if cmd == 1:
        # DSK2 write-protect mask (+3): the unit bit must be SET or the
        # controller silently discards the write (Meisaka DSK2 model).
        a.ldab_i(0xFF).stab_z(3)
    a.ldab_i(cmd).stab_z(8)          # 0 = read, 1 = write
    a.jsr_abs("hawk_busy")
    a.xfrb_au_al()                   # AL = F144 status byte
    a.rsr()


def emit_hawk_read_block(a):
    _emit_hawk_block(a, "read_block", 0)


def emit_hawk_write_block(a):
    _emit_hawk_block(a, "write_block", 1)
