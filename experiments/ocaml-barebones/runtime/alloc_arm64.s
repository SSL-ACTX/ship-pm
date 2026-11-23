	.text
	.align 3

	.globl caml_alloc2
	.type caml_alloc2, %function
caml_alloc2:
	ldr x16, [x28]
	sub x27, x27, #24
	cmp x27, x16
	b.lo .Lalloc_gc2
	ret
.Lalloc_gc2:
	b caml_call_gc

	.globl caml_alloc3
	.type caml_alloc3, %function
caml_alloc3:
	ldr x16, [x28]
	sub x27, x27, #32
	cmp x27, x16
	b.lo .Lalloc_gc3
	ret
.Lalloc_gc3:
	b caml_call_gc

	.globl caml_allocN
	.type caml_allocN, %function
caml_allocN:
	ldr x16, [x28]
	sub x27, x27, x8
	cmp x27, x16
	b.lo .Lalloc_gcN
	ret
.Lalloc_gcN:
	b caml_call_gc
