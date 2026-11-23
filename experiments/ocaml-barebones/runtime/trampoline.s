	.text
	.align 3
	.globl call_ocaml_init
	.type call_ocaml_init, %function
call_ocaml_init:
	stp x29, x30, [sp, #-48]!
	mov x29, sp
	stp x19, x20, [sp, #16]
	stp x27, x28, [sp, #32]

	mov x19, x0
	mov x28, x1
	mov x27, x2
	blr x19

	ldp x27, x28, [sp, #32]
	ldp x19, x20, [sp, #16]
	ldp x29, x30, [sp], #48
	ret

	.globl call_ocaml_func
	.type call_ocaml_func, %function
call_ocaml_func:
	stp x29, x30, [sp, #-48]!
	mov x29, sp
	stp x19, x20, [sp, #16]
	stp x27, x28, [sp, #32]

	mov x19, x0
	mov x28, x1
	mov x27, x2
	mov x0, x3
	blr x19

	ldp x27, x28, [sp, #32]
	ldp x19, x20, [sp, #16]
	ldp x29, x30, [sp], #48
	ret

	/* caml_c_call */
	.globl caml_c_call
	.type caml_c_call, %function
caml_c_call:
	stp x29, x30, [sp, #-16]!
	mov x29, sp
	blr x8
	ldp x29, x30, [sp], #16
	ret

	/* caml_reperform stub */
	.globl caml_reperform
	.type caml_reperform, %function
caml_reperform:
	b caml_perform
