	.file	""
	.data
	.globl	camlNano.data_begin
camlNano.data_begin:
	.text
	.globl	camlNano.code_begin
camlNano.code_begin:
	.data
	.align	3
	.data
	.align	3
	.quad	4087
	.globl	camlNano.3
camlNano.3:
	.quad	caml_tuplify2
	.quad	-144115188075855865
	.quad	camlNano.fst_38
	.data
	.align	3
	.quad	4087
	.globl	camlNano.2
camlNano.2:
	.quad	caml_tuplify2
	.quad	-144115188075855865
	.quad	camlNano.snd_42
	.data
	.align	3
	.quad	3063
	.globl	camlNano.1
camlNano.1:
	.quad	camlNano.id_46
	.quad	72057594037927941
	.data
	.align	3
	.quad	3840
	.globl	camlNano
	.globl	camlNano
camlNano:
	.quad	1
	.quad	1
	.quad	1
	.data
	.align	3
	.globl	camlNano.gc_roots
	.globl	camlNano.gc_roots
camlNano.gc_roots:
	.quad	camlNano
	.quad	0
	.text
	.align	3
	.globl	camlNano.fst_38
	.type	camlNano.fst_38, %function
camlNano.fst_38:
	.cfi_startproc
.L101:
.L102:
.L100:
	.ifgt (. - .L102) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L103:
	ret
	.ifgt (. - .L103) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L101) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.cfi_endproc
	.type	camlNano.fst_38, %function
	.size	camlNano.fst_38, . - camlNano.fst_38
	.text
	.align	3
	.globl	camlNano.snd_42
	.type	camlNano.snd_42, %function
camlNano.snd_42:
	.cfi_startproc
.L105:
.L106:
.L104:
	.ifgt (. - .L106) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L107:
	mov	x0, x1
	.ifgt (. - .L107) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L108:
	ret
	.ifgt (. - .L108) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L105) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.cfi_endproc
	.type	camlNano.snd_42, %function
	.size	camlNano.snd_42, . - camlNano.snd_42
	.text
	.align	3
	.globl	camlNano.id_46
	.type	camlNano.id_46, %function
camlNano.id_46:
	.cfi_startproc
.L110:
.L111:
.L109:
	.ifgt (. - .L111) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L112:
	ret
	.ifgt (. - .L112) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L110) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.cfi_endproc
	.type	camlNano.id_46, %function
	.size	camlNano.id_46, . - camlNano.id_46
	.text
	.align	3
	.globl	camlNano.entry
	.type	camlNano.entry, %function
camlNano.entry:
	.cfi_startproc
.L114:
.L115:
	str	x30, [sp, #-8]
	.cfi_offset 30, -8
	sub	sp, sp, #16
	.cfi_adjust_cfa_offset	16
	.ifgt (. - .L115) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L116:
.L113:
	.ifgt (. - .L116) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L117:
	adrp	x1, :got:camlNano.3
	ldr	x1, [x1, #:got_lo12:camlNano.3]
	.ifgt (. - .L117) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L118:
	adrp	x0, :got:camlNano
	ldr	x0, [x0, #:got_lo12:camlNano]
	.ifgt (. - .L118) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L119:
	mov	x19, sp
	.cfi_remember_state
	.cfi_def_cfa_register 19
	ldr	x16, [x28, 64]
	mov	sp, x16
	bl	caml_initialize
	mov	sp, x19
	.cfi_restore_state
	.ifgt (. - .L119) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L120:
	adrp	x1, :got:camlNano.2
	ldr	x1, [x1, #:got_lo12:camlNano.2]
	.ifgt (. - .L120) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L121:
	adrp	x3, :got:camlNano
	ldr	x3, [x3, #:got_lo12:camlNano]
	.ifgt (. - .L121) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L122:
	add	x0, x3, #8
	.ifgt (. - .L122) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L123:
	mov	x19, sp
	.cfi_remember_state
	.cfi_def_cfa_register 19
	ldr	x16, [x28, 64]
	mov	sp, x16
	bl	caml_initialize
	mov	sp, x19
	.cfi_restore_state
	.ifgt (. - .L123) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L124:
	adrp	x1, :got:camlNano.1
	ldr	x1, [x1, #:got_lo12:camlNano.1]
	.ifgt (. - .L124) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L125:
	adrp	x6, :got:camlNano
	ldr	x6, [x6, #:got_lo12:camlNano]
	.ifgt (. - .L125) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L126:
	add	x0, x6, #16
	.ifgt (. - .L126) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L127:
	mov	x19, sp
	.cfi_remember_state
	.cfi_def_cfa_register 19
	ldr	x16, [x28, 64]
	mov	sp, x16
	bl	caml_initialize
	mov	sp, x19
	.cfi_restore_state
	.ifgt (. - .L127) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L128:
	orr	x0, xzr, #1
	.ifgt (. - .L128) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L129:
	.ifgt (. - .L129) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L130:
	add	sp, sp, #16
	.cfi_adjust_cfa_offset	-16
	ldr	x30, [sp, #-8]
	ret
	.cfi_adjust_cfa_offset	16
	.ifgt (. - .L130) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L114) - 140
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.cfi_endproc
	.type	camlNano.entry, %function
	.size	camlNano.entry, . - camlNano.entry
	.data
	.align	3
	.text
	.globl	camlNano.code_end
camlNano.code_end:
	.data
	.quad	0
	.globl	camlNano.data_end
camlNano.data_end:
	.quad	0
	.align	3
	.globl	camlNano.frametable
camlNano.frametable:
	.quad	0
	.align	3
	.type	camlNano.frametable, %object
	.size	camlNano.frametable, . - camlNano.frametable
	.section .note.GNU-stack,"",%progbits
