	.file	""
	.data
	.globl	camlNano_effects.data_begin
camlNano_effects.data_begin:
	.text
	.globl	camlNano_effects.code_begin
camlNano_effects.code_begin:
	.data
	.align	3
	.data
	.align	3
	.quad	3063
	.globl	camlNano_effects.6
camlNano_effects.6:
	.quad	camlNano_effects.fun_100
	.quad	72057594037927941
	.data
	.align	3
	.quad	3063
	.globl	camlNano_effects.5
camlNano_effects.5:
	.quad	camlNano_effects.fun_110
	.quad	72057594037927941
	.data
	.align	3
	.quad	3063
	.globl	camlNano_effects.4
camlNano_effects.4:
	.quad	camlNano_effects.fun_108
	.quad	72057594037927941
	.data
	.align	3
	.quad	4087
	.globl	camlNano_effects.3
camlNano_effects.3:
	.quad	caml_curry2
	.quad	144115188075855879
	.quad	camlNano_effects.continue_45
	.data
	.align	3
	.quad	4087
	.globl	camlNano_effects.2
camlNano_effects.2:
	.quad	caml_curry3
	.quad	216172782113783815
	.quad	camlNano_effects.match_with_57
	.data
	.align	3
	.quad	4087
	.globl	camlNano_effects.1
camlNano_effects.1:
	.quad	caml_curry3
	.quad	216172782113783815
	.quad	camlNano_effects.try_with_69
	.data
	.align	3
	.quad	4864
	.globl	camlNano_effects
	.globl	camlNano_effects
camlNano_effects:
	.quad	1
	.quad	1
	.quad	1
	.quad	1
	.data
	.align	3
	.globl	camlNano_effects.gc_roots
	.globl	camlNano_effects.gc_roots
camlNano_effects.gc_roots:
	.quad	camlNano_effects
	.quad	0
	.text
	.align	3
	.globl	camlNano_effects.continue_45
	.type	camlNano_effects.continue_45, %function
camlNano_effects.continue_45:
	.cfi_startproc
.L101:
.L102:
	str	x30, [sp, #-8]
	.cfi_offset 30, -8
	sub	sp, sp, #16
	.cfi_adjust_cfa_offset	16
	.ifgt (. - .L102) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L103:
.L100:
	.ifgt (. - .L103) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L104:
	mov	x20, x1
	.ifgt (. - .L104) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L105:
	ldr	x21, [x0, #8]
	.ifgt (. - .L105) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L106:
	mov	x19, sp
	.cfi_remember_state
	.cfi_def_cfa_register 19
	ldr	x16, [x28, 64]
	mov	sp, x16
	bl	caml_continuation_use_noexc
	mov	sp, x19
	.cfi_restore_state
	.ifgt (. - .L106) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L107:
	adrp	x1, :got:camlNano_effects.6
	ldr	x1, [x1, #:got_lo12:camlNano_effects.6]
	.ifgt (. - .L107) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L108:
	mov	x2, x20
	.ifgt (. - .L108) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L109:
	mov	x3, x21
	.ifgt (. - .L109) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L110:
	add	sp, sp, #16
	.cfi_adjust_cfa_offset	-16
	ldr	x30, [sp, #-8]
	b	caml_resume
	.cfi_adjust_cfa_offset	16
	.ifgt (. - .L110) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L101) - 64
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.cfi_endproc
	.type	camlNano_effects.continue_45, %function
	.size	camlNano_effects.continue_45, . - camlNano_effects.continue_45
	.text
	.align	3
	.globl	camlNano_effects.fun_100
	.type	camlNano_effects.fun_100, %function
camlNano_effects.fun_100:
	.cfi_startproc
.L112:
.L113:
.L111:
	.ifgt (. - .L113) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L114:
	ret
	.ifgt (. - .L114) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L112) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.cfi_endproc
	.type	camlNano_effects.fun_100, %function
	.size	camlNano_effects.fun_100, . - camlNano_effects.fun_100
	.text
	.align	3
	.globl	camlNano_effects.match_with_57
	.type	camlNano_effects.match_with_57, %function
camlNano_effects.match_with_57:
	.cfi_startproc
.L116:
.L117:
	str	x30, [sp, #-8]
	.cfi_offset 30, -8
	sub	sp, sp, #32
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L117) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L118:
.L115:
	.ifgt (. - .L118) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L119:
	str	x0, [sp, #0]
	.ifgt (. - .L119) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L120:
	str	x1, [sp, #8]
	.ifgt (. - .L120) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L121:
	ldr	x16, [x28, #0]
	sub	x27, x27, #40
	cmp	x27, x16
	b.lo	.L124
.L123:	add	x3, x27, #8
	.ifgt (. - .L121) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L125:
	movz	x4, #4343, lsl #0
	.ifgt (. - .L125) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L126:
	str	x4, [x3, #-8]
	.ifgt (. - .L126) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L127:
	adrp	x5, :got:caml_curry3
	ldr	x5, [x5, #:got_lo12:caml_curry3]
	.ifgt (. - .L127) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L128:
	str	x5, [x3, #0]
	.ifgt (. - .L128) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L129:
	movz	x6, #7, lsl #0
	movk	x6, #768, lsl #48
	.ifgt (. - .L129) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L130:
	str	x6, [x3, #8]
	.ifgt (. - .L130) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L131:
	adrp	x7, :got:camlNano_effects.effc_62
	ldr	x7, [x7, #:got_lo12:camlNano_effects.effc_62]
	.ifgt (. - .L131) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L132:
	str	x7, [x3, #16]
	.ifgt (. - .L132) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L133:
	str	x2, [x3, #24]
	.ifgt (. - .L133) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L134:
	ldr	x1, [x2, #8]
	.ifgt (. - .L134) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L135:
	ldr	x0, [x2, #0]
	.ifgt (. - .L135) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L136:
	mov	x2, x3
	.ifgt (. - .L136) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L137:
	adrp	x8, :got:caml_alloc_stack
	ldr	x8, [x8, #:got_lo12:caml_alloc_stack]
	bl	caml_c_call
.L138:
	.ifgt (. - .L137) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L139:
	ldr	x1, [sp, #0]
	.ifgt (. - .L139) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L140:
	ldr	x2, [sp, #8]
	.ifgt (. - .L140) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L141:
	add	sp, sp, #32
	.cfi_adjust_cfa_offset	-32
	ldr	x30, [sp, #-8]
	b	caml_runstack
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L141) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L116) - 128
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L124:	bl	caml_call_gc
.L122:	b	.L123
	.cfi_endproc
	.type	camlNano_effects.match_with_57, %function
	.size	camlNano_effects.match_with_57, . - camlNano_effects.match_with_57
	.text
	.align	3
	.globl	camlNano_effects.effc_62
	.type	camlNano_effects.effc_62, %function
.L144:
	mov	x16, #36
	stp	x16, x30, [sp, #-16]!
	bl	caml_call_realloc_stack
	ldp	x16, x30, [sp], #16
camlNano_effects.effc_62:
	.cfi_startproc
	ldr	x16, [x28, #40]
	add	x16, x16, #344
	cmp	sp, x16
	bcc	.L144
.L145:
.L146:
	str	x30, [sp, #-8]
	.cfi_offset 30, -8
	sub	sp, sp, #32
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L146) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L147:
.L143:
	.ifgt (. - .L147) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L148:
	str	x0, [sp, #0]
	.ifgt (. - .L148) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L149:
	str	x1, [sp, #8]
	.ifgt (. - .L149) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L150:
	str	x2, [sp, #16]
	.ifgt (. - .L150) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L151:
	ldr	x16, [x28, #0]
	cmp	x27, x16
	b.ls	.L153
.L154:
	.ifgt (. - .L151) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L155:
	ldr	x4, [x3, #24]
	.ifgt (. - .L155) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L156:
	ldr	x1, [x4, #16]
	.ifgt (. - .L156) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L157:
	ldr	x6, [x1, #0]
	.ifgt (. - .L157) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L158:
	blr	x6
.L159:
	.ifgt (. - .L158) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L160:
	tbz	x0, #0, .L142
	.ifgt (. - .L160) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L161:
	ldr	x0, [sp, #0]
	.ifgt (. - .L161) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L162:
	ldr	x1, [sp, #8]
	.ifgt (. - .L162) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L163:
	ldr	x2, [sp, #16]
	.ifgt (. - .L163) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L164:
	add	sp, sp, #32
	.cfi_adjust_cfa_offset	-32
	ldr	x30, [sp, #-8]
	b	caml_reperform
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L164) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L165:
.L142:
	.ifgt (. - .L165) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L166:
	ldr	x1, [x0, #0]
	.ifgt (. - .L166) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L167:
	ldr	x9, [x1, #0]
	.ifgt (. - .L167) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L168:
	ldr	x0, [sp, #8]
	.ifgt (. - .L168) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L169:
	add	sp, sp, #32
	.cfi_adjust_cfa_offset	-32
	ldr	x30, [sp, #-8]
	br	x9
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L169) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L145) - 100
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L153:	bl	caml_call_gc
.L152:	b	.L154
	.cfi_endproc
	.type	camlNano_effects.effc_62, %function
	.size	camlNano_effects.effc_62, . - camlNano_effects.effc_62
	.text
	.align	3
	.globl	camlNano_effects.try_with_69
	.type	camlNano_effects.try_with_69, %function
camlNano_effects.try_with_69:
	.cfi_startproc
.L171:
.L172:
	str	x30, [sp, #-8]
	.cfi_offset 30, -8
	sub	sp, sp, #32
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L172) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L173:
.L170:
	.ifgt (. - .L173) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L174:
	str	x0, [sp, #0]
	.ifgt (. - .L174) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L175:
	str	x1, [sp, #8]
	.ifgt (. - .L175) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L176:
	ldr	x16, [x28, #0]
	sub	x27, x27, #40
	cmp	x27, x16
	b.lo	.L179
.L178:	add	x3, x27, #8
	.ifgt (. - .L176) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L180:
	movz	x4, #4343, lsl #0
	.ifgt (. - .L180) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L181:
	str	x4, [x3, #-8]
	.ifgt (. - .L181) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L182:
	adrp	x5, :got:caml_curry3
	ldr	x5, [x5, #:got_lo12:caml_curry3]
	.ifgt (. - .L182) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L183:
	str	x5, [x3, #0]
	.ifgt (. - .L183) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L184:
	movz	x6, #7, lsl #0
	movk	x6, #768, lsl #48
	.ifgt (. - .L184) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L185:
	str	x6, [x3, #8]
	.ifgt (. - .L185) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L186:
	adrp	x7, :got:camlNano_effects.effc$27_74
	ldr	x7, [x7, #:got_lo12:camlNano_effects.effc$27_74]
	.ifgt (. - .L186) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L187:
	str	x7, [x3, #16]
	.ifgt (. - .L187) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L188:
	str	x2, [x3, #24]
	.ifgt (. - .L188) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L189:
	adrp	x1, :got:camlNano_effects.5
	ldr	x1, [x1, #:got_lo12:camlNano_effects.5]
	.ifgt (. - .L189) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L190:
	adrp	x0, :got:camlNano_effects.4
	ldr	x0, [x0, #:got_lo12:camlNano_effects.4]
	.ifgt (. - .L190) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L191:
	mov	x2, x3
	.ifgt (. - .L191) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L192:
	adrp	x8, :got:caml_alloc_stack
	ldr	x8, [x8, #:got_lo12:caml_alloc_stack]
	bl	caml_c_call
.L193:
	.ifgt (. - .L192) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L194:
	ldr	x1, [sp, #0]
	.ifgt (. - .L194) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L195:
	ldr	x2, [sp, #8]
	.ifgt (. - .L195) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L196:
	add	sp, sp, #32
	.cfi_adjust_cfa_offset	-32
	ldr	x30, [sp, #-8]
	b	caml_runstack
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L196) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L171) - 136
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L179:	bl	caml_call_gc
.L177:	b	.L178
	.cfi_endproc
	.type	camlNano_effects.try_with_69, %function
	.size	camlNano_effects.try_with_69, . - camlNano_effects.try_with_69
	.text
	.align	3
	.globl	camlNano_effects.effc$27_74
	.type	camlNano_effects.effc$27_74, %function
.L199:
	mov	x16, #36
	stp	x16, x30, [sp, #-16]!
	bl	caml_call_realloc_stack
	ldp	x16, x30, [sp], #16
camlNano_effects.effc$27_74:
	.cfi_startproc
	ldr	x16, [x28, #40]
	add	x16, x16, #344
	cmp	sp, x16
	bcc	.L199
.L200:
.L201:
	str	x30, [sp, #-8]
	.cfi_offset 30, -8
	sub	sp, sp, #32
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L201) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L202:
.L198:
	.ifgt (. - .L202) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L203:
	str	x0, [sp, #0]
	.ifgt (. - .L203) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L204:
	str	x1, [sp, #8]
	.ifgt (. - .L204) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L205:
	str	x2, [sp, #16]
	.ifgt (. - .L205) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L206:
	ldr	x16, [x28, #0]
	cmp	x27, x16
	b.ls	.L208
.L209:
	.ifgt (. - .L206) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L210:
	ldr	x4, [x3, #24]
	.ifgt (. - .L210) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L211:
	ldr	x1, [x4, #0]
	.ifgt (. - .L211) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L212:
	ldr	x6, [x1, #0]
	.ifgt (. - .L212) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L213:
	blr	x6
.L214:
	.ifgt (. - .L213) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L215:
	tbz	x0, #0, .L197
	.ifgt (. - .L215) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L216:
	ldr	x0, [sp, #0]
	.ifgt (. - .L216) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L217:
	ldr	x1, [sp, #8]
	.ifgt (. - .L217) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L218:
	ldr	x2, [sp, #16]
	.ifgt (. - .L218) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L219:
	add	sp, sp, #32
	.cfi_adjust_cfa_offset	-32
	ldr	x30, [sp, #-8]
	b	caml_reperform
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L219) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L220:
.L197:
	.ifgt (. - .L220) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L221:
	ldr	x1, [x0, #0]
	.ifgt (. - .L221) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L222:
	ldr	x9, [x1, #0]
	.ifgt (. - .L222) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L223:
	ldr	x0, [sp, #8]
	.ifgt (. - .L223) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L224:
	add	sp, sp, #32
	.cfi_adjust_cfa_offset	-32
	ldr	x30, [sp, #-8]
	br	x9
	.cfi_adjust_cfa_offset	32
	.ifgt (. - .L224) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L200) - 100
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L208:	bl	caml_call_gc
.L207:	b	.L209
	.cfi_endproc
	.type	camlNano_effects.effc$27_74, %function
	.size	camlNano_effects.effc$27_74, . - camlNano_effects.effc$27_74
	.text
	.align	3
	.globl	camlNano_effects.fun_108
	.type	camlNano_effects.fun_108, %function
camlNano_effects.fun_108:
	.cfi_startproc
.L226:
.L227:
.L225:
	.ifgt (. - .L227) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L228:
	ret
	.ifgt (. - .L228) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L226) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.cfi_endproc
	.type	camlNano_effects.fun_108, %function
	.size	camlNano_effects.fun_108, . - camlNano_effects.fun_108
	.text
	.align	3
	.globl	camlNano_effects.fun_110
	.type	camlNano_effects.fun_110, %function
camlNano_effects.fun_110:
	.cfi_startproc
.L230:
.L231:
.L229:
	.ifgt (. - .L231) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L232:
	mov	sp, x26
	ldp	x26, x16, [sp], 16
	br	x16
	.ifgt (. - .L232) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L230) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.cfi_endproc
	.type	camlNano_effects.fun_110, %function
	.size	camlNano_effects.fun_110, . - camlNano_effects.fun_110
	.text
	.align	3
	.globl	camlNano_effects.entry
	.type	camlNano_effects.entry, %function
camlNano_effects.entry:
	.cfi_startproc
.L234:
.L235:
	str	x30, [sp, #-8]
	.cfi_offset 30, -8
	sub	sp, sp, #16
	.cfi_adjust_cfa_offset	16
	.ifgt (. - .L235) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L236:
.L233:
	.ifgt (. - .L236) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L237:
	adrp	x1, :got:camlNano_effects.3
	ldr	x1, [x1, #:got_lo12:camlNano_effects.3]
	.ifgt (. - .L237) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L238:
	adrp	x2, :got:camlNano_effects
	ldr	x2, [x2, #:got_lo12:camlNano_effects]
	.ifgt (. - .L238) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L239:
	add	x0, x2, #8
	.ifgt (. - .L239) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L240:
	mov	x19, sp
	.cfi_remember_state
	.cfi_def_cfa_register 19
	ldr	x16, [x28, 64]
	mov	sp, x16
	bl	caml_initialize
	mov	sp, x19
	.cfi_restore_state
	.ifgt (. - .L240) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L241:
	adrp	x1, :got:camlNano_effects.2
	ldr	x1, [x1, #:got_lo12:camlNano_effects.2]
	.ifgt (. - .L241) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L242:
	adrp	x4, :got:camlNano_effects
	ldr	x4, [x4, #:got_lo12:camlNano_effects]
	.ifgt (. - .L242) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L243:
	add	x0, x4, #16
	.ifgt (. - .L243) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L244:
	mov	x19, sp
	.cfi_remember_state
	.cfi_def_cfa_register 19
	ldr	x16, [x28, 64]
	mov	sp, x16
	bl	caml_initialize
	mov	sp, x19
	.cfi_restore_state
	.ifgt (. - .L244) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L245:
	adrp	x1, :got:camlNano_effects.1
	ldr	x1, [x1, #:got_lo12:camlNano_effects.1]
	.ifgt (. - .L245) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L246:
	adrp	x7, :got:camlNano_effects
	ldr	x7, [x7, #:got_lo12:camlNano_effects]
	.ifgt (. - .L246) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L247:
	add	x0, x7, #24
	.ifgt (. - .L247) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L248:
	mov	x19, sp
	.cfi_remember_state
	.cfi_def_cfa_register 19
	ldr	x16, [x28, 64]
	mov	sp, x16
	bl	caml_initialize
	mov	sp, x19
	.cfi_restore_state
	.ifgt (. - .L248) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L249:
	bl	caml_alloc3
.L250:	add	x1, x27, #8
	.ifgt (. - .L249) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L251:
	orr	x10, xzr, #3072
	.ifgt (. - .L251) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L252:
	str	x10, [x1, #-8]
	.ifgt (. - .L252) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L253:
	adrp	x0, :got:camlNano_effects
	ldr	x0, [x0, #:got_lo12:camlNano_effects]
	.ifgt (. - .L253) - 8
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L254:
	ldr	x12, [x0, #8]
	.ifgt (. - .L254) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L255:
	str	x12, [x1, #0]
	.ifgt (. - .L255) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L256:
	ldr	x14, [x0, #16]
	.ifgt (. - .L256) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L257:
	str	x14, [x1, #8]
	.ifgt (. - .L257) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L258:
	ldr	x19, [x0, #24]
	.ifgt (. - .L258) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L259:
	str	x19, [x1, #16]
	.ifgt (. - .L259) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L260:
	mov	x19, sp
	.cfi_remember_state
	.cfi_def_cfa_register 19
	ldr	x16, [x28, 64]
	mov	sp, x16
	bl	caml_initialize
	mov	sp, x19
	.cfi_restore_state
	.ifgt (. - .L260) - 20
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L261:
	orr	x0, xzr, #1
	.ifgt (. - .L261) - 4
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L262:
	.ifgt (. - .L262) - 0
	.error "Emit.instr_size: instruction length mismatch"
	.endif
.L263:
	add	sp, sp, #16
	.cfi_adjust_cfa_offset	-16
	ldr	x30, [sp, #-8]
	ret
	.cfi_adjust_cfa_offset	16
	.ifgt (. - .L263) - 12
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.ifgt (. - .L234) - 212
	.error "Emit.instr_size: instruction length mismatch"
	.endif
	.cfi_endproc
	.type	camlNano_effects.entry, %function
	.size	camlNano_effects.entry, . - camlNano_effects.entry
	.data
	.align	3
	.quad	caml_alloc_stack
	.quad	caml_continuation_use_noexc
	.text
	.globl	camlNano_effects.code_end
camlNano_effects.code_end:
	.data
	.quad	0
	.globl	camlNano_effects.data_end
camlNano_effects.data_end:
	.quad	0
	.align	3
	.globl	camlNano_effects.frametable
camlNano_effects.frametable:
	.quad	9
	.type	.L250, %function
	.quad	.L250
	.short	18
	.short	0
	.byte	1
	.byte	2
	.align	3
	.type	.L214, %function
	.quad	.L214
	.short	33
	.short	2
	.short	0
	.short	8
	.align	2
	.long	.L264 - . + 0x0
	.align	3
	.type	.L207, %function
	.quad	.L207
	.short	34
	.short	4
	.short	0
	.short	1
	.short	7
	.short	8
	.byte	0
	.align	3
	.type	.L193, %function
	.quad	.L193
	.short	33
	.short	2
	.short	0
	.short	8
	.align	2
	.long	.L265 - . + 0x0
	.align	3
	.type	.L177, %function
	.quad	.L177
	.short	34
	.short	3
	.short	0
	.short	5
	.short	8
	.byte	1
	.byte	3
	.align	3
	.type	.L159, %function
	.quad	.L159
	.short	33
	.short	2
	.short	0
	.short	8
	.align	2
	.long	.L266 - . + 0x0
	.align	3
	.type	.L152, %function
	.quad	.L152
	.short	34
	.short	4
	.short	0
	.short	1
	.short	7
	.short	8
	.byte	0
	.align	3
	.type	.L138, %function
	.quad	.L138
	.short	33
	.short	2
	.short	0
	.short	8
	.align	2
	.long	.L267 - . + 0x0
	.align	3
	.type	.L122, %function
	.quad	.L122
	.short	34
	.short	3
	.short	0
	.short	5
	.short	8
	.byte	1
	.byte	3
	.align	3
	.align	2
.L267:
	.long	.L269 - . + 0x0
	.long	0x16031b0
	.align	2
.L264:
	.long	.L270 - . + 0x0
	.long	0x18830e0
	.align	2
.L266:
	.long	.L271 - . + 0x0
	.long	0x14030e0
	.align	2
.L265:
	.long	.L272 - . + 0x0
	.long	0x1a831e8
.L268:
	.asciz	"nanolib/nano_effects.ml"
	.align	2
.L269:
	.long	.L268 - . + 0x0
	.asciz	"Nano_effects.Deep.match_with"
	.align	2
.L271:
	.long	.L268 - . + 0x0
	.asciz	"Nano_effects.Deep.match_with.effc"
	.align	2
.L272:
	.long	.L268 - . + 0x0
	.asciz	"Nano_effects.Deep.try_with"
	.align	2
.L270:
	.long	.L268 - . + 0x0
	.asciz	"Nano_effects.Deep.try_with.effc'"
	.align	3
	.type	camlNano_effects.frametable, %object
	.size	camlNano_effects.frametable, . - camlNano_effects.frametable
	.section .note.GNU-stack,"",%progbits
