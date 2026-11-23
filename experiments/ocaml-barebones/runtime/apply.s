	.text
	.align 3
	.globl caml_apply2
	.type caml_apply2, %function
caml_apply2:
	sub sp, sp, #32
	str x30, [sp, #24]
	str x19, [sp, #16]
	str x20, [sp, #8]
	str x21, [sp]

	// x0: a1, x1: a2, x2: clos
	ldr x4, [x2, #8]
	asr x5, x4, #56
	cmp x5, #2
	b.ne .Lapply2_curry
	// Arity matches: direct jump!
	ldr x11, [x2, #16]
	ldr x21, [sp]
	ldr x20, [sp, #8]
	ldr x19, [sp, #16]
	ldr x30, [sp, #24]
	add sp, sp, #32
	br x11

.Lapply2_curry:
	mov x19, x1 // save a2
	mov x20, x2 // save clos
	mov x1, x20 // clos in x1
	ldr x6, [x20, #0]
	blr x6

	mov x1, x0  // clos1 in x1
	mov x0, x19 // a2 in x0
	ldr x8, [x1, #0]
	blr x8

	ldr x21, [sp]
	ldr x20, [sp, #8]
	ldr x19, [sp, #16]
	ldr x30, [sp, #24]
	add sp, sp, #32
	ret

	.globl caml_apply3
	.type caml_apply3, %function
caml_apply3:
	sub sp, sp, #32
	str x30, [sp, #24]

	// Check arity
	ldr x4, [x3, #8]
	asr x5, x4, #56
	cmp x5, #3
	b.ne .Lapply3_curry

	// Direct call
	ldr x11, [x3, #16]
	add sp, sp, #32
	// x3 remains clos
	br x11

.Lapply3_curry:
	str x2, [sp, #8]
	str x1, [sp]
	ldr x6, [x3]
	mov x1, x3
	blr x6

	mov x1, x0
	ldr x8, [x1]
	ldr x0, [sp]
	blr x8

	mov x1, x0
	ldr x10, [x1]
	ldr x0, [sp, #8]
	add sp, sp, #32
	ldr x30, [sp, #-8]
	br x10
