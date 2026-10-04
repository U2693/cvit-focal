def emit_disk6_read_block(a):
    """Emit KERNEL read_block: read one 400-byte Disk6 floppy sector via FFC.

    BX points at:
      +0 unit, +1 track, +2 sector, +3 head, +4 u16 destination.
    The caller supplies Disk6 CHS (logical sector N => track N/20, sector N%20
    for the default 20-sector geometry).  AL returns the FFC result byte.
    """
    cmd = 0x2EE0
    a.label("read_block")
    # Build an FFC command buffer in RAM.
    a.ldab_i(0x81).stab_d(cmd + 0)
    a.ldab_bx(0).stab_d(cmd + 1)
    a.ldab_i(0x83).stab_d(cmd + 2)
    a.ldab_bx(1).stab_d(cmd + 3)
    a.ldab_i(0x85).stab_d(cmd + 4)
    a.ldab_bx(3).stab_d(cmd + 5)
    a.ldab_i(0x88).stab_d(cmd + 6)
    a.ldab_bx(2).stab_d(cmd + 7)
    a.ldab_i(0x00).stab_d(cmd + 8)
    a.ldab_i(0x01).stab_d(cmd + 9)
    a.ldab_i(0x90).stab_d(cmd + 10)
    a.ldab_i(0xFF).stab_d(cmd + 11)

    # DMA command bytes to the FFC, then execute with data DMA to CB+4.
    a.lda_i(cmd).dma_sad_a()
    a.lda_i(0xFFF3).dma_sct_a()      # -12 -> 12-byte command buffer
    a.dma_sdv_0().dma_eab()
    a.ldab_i(0x43).stab_d(0xF800)
    a.lda_bx(4).dma_sad_a()
    a.lda_i(0xFE6F).dma_sct_a()      # -401 -> 400-byte sector
    a.dma_sdv_0().dma_eab()
    a.ldab_i(0x45).stab_d(0xF800)
    a.ldab_d(0xF800)
    a.ldbb_i(0).sabb().bnz("disk6_read_error")
    a.rsr()
    a.label("disk6_read_error")
    a.print("\r\nDISK6 READ ERROR\r\n")
    a.ldab_d(0xF800)
    a.rsr()
