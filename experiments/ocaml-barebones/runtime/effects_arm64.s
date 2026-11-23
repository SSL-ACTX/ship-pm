	.text
	.align 3

/* Macro: switch between OCaml stacks
   old_stack: register pointing to old struct stack_info
   new_stack: register pointing to new struct stack_info
   clobbers x16 (TMP) and switches x26 (TRAP_PTR) */
.macro SWITCH_STACKS old_stk, new_stk
	// Save caller frame and return address on current stack
	stp x29, x30, [sp, #-16]!
	mov x29, sp

	// Save SP and TRAP_PTR to old_stk
	mov x16, sp
	str x16, [\old_stk]       // Stack_sp is offset 0
	str x26, [\old_stk, #8]   // Stack_exception is offset 8

	// Switch domain current_stack (offset 40 in caml_domain_state)
	str \new_stk, [x28, #40]

	// Load SP and TRAP_PTR from new_stk
	ldr x16, [\new_stk]
	mov sp, x16
	ldr x26, [\new_stk, #8]

	// Restore frame and return address from new stack
	ldp x29, x30, [sp], #16
.endm

/* caml_perform
   x0: effect to perform
   x1: freshly allocated continuation */
	.globl caml_perform
	.type caml_perform, %function
caml_perform:
	ldr x2, [x28, #40]         // x2 := current_stack (old stack)
	add x3, x2, #1             // x3 := Val_ptr(old stack)
	str x3, [x1]               // cont[0] = old stack
	str x3, [x1, #8]           // cont[1] = last_fiber

	ldr x9, [x2, #16]          // x9 := old_stack->handler
	ldr x10, [x9, #24]         // x10 := handler->parent
	cbz x10, .Lunhandled_effect

	// Switch from old_stack (x2) to parent stack (x10)
	SWITCH_STACKS x2, x10

	// Null out parent of old handler after switch
	str xzr, [x9, #24]
	ldr x16, [x9, #16]         // x16 := handler->handle_effect

	mov x2, x3                 // x2 := last_fiber
	mov x3, x16                // x3 := effect handler closure
	// Invoke caml_apply3(eff, cont, last_fiber, handler_clos)
	b caml_apply3

.Lunhandled_effect:
	// Unhandled effect: reload performer and abort
	ldr x10, [x1]
	sub x10, x10, #1
	ldr x9, [x28, #40]
	SWITCH_STACKS x9, x10
	mov x0, x16
	bl caml_raise_unhandled_effect
	ret

/* caml_resume
   x0: new fiber
   x1: fun (resume_fun: identity or raise)
   x2: arg (resumed value)
   x3: last_fiber */
	.globl caml_resume
	.type caml_resume, %function
caml_resume:
	sub x0, x0, #1             // x0 = Ptr_val(new fiber)
	ldr x4, [x1]               // code pointer of resume_fun
	cbz x0, .Lcontinuation_already_resumed

	sub x3, x3, #1             // x3 = Ptr_val(last_fiber)
	ldr x8, [x3, #16]          // x8 = last_fiber->handler
	ldr x9, [x28, #40]         // x9 = current_stack
	str x9, [x8, #24]          // last_fiber->handler->parent = current_stack

	SWITCH_STACKS x9, x0

	mov x0, x2                 // arg in x0
	br x4                      // jump to resume_fun

.Lcontinuation_already_resumed:
	bl caml_raise_continuation_already_resumed
	ret

/* caml_runstack
   x0: fiber
   x1: fun
   x2: arg */
	.globl caml_runstack
	.type caml_runstack, %function
caml_runstack:
	stp x29, x30, [sp, #-48]!
	mov x29, sp
	stp x19, x20, [sp, #16]
	stp x21, x22, [sp, #32]

	sub x0, x0, #1             // x0 := Ptr_val(fiber)
	ldr x3, [x1]               // code pointer of fun

	ldr x8, [x28, #40]         // x8 := old current_stack
	mov x16, sp
	str x16, [x8]              // old_stack->sp = sp
	str x26, [x8, #8]          // old_stack->exception_ptr = TRAP_PTR

	ldr x16, [x0, #16]         // x16 := new_stack->handler
	str x8, [x16, #24]         // new_stack->handler->parent = old_stack
	str x0, [x28, #40]         // current_stack = new_stack

	ldr x9, [x0]               // x9 := new_stack->sp
	sub x9, x9, #32            // allocate fiber exception frame
	adr x16, .Lfiber_exn_handler
	str x16, [x9, #8]
	ldr x16, [x0, #8]
	str x16, [x9]
	mov x26, x9                // TRAP_PTR = x9
	mov sp, x9

	// Call function on new fiber stack
	mov x0, x2
	blr x3

.Lframe_runstack:
	add x8, sp, #32            // x8 := stack_handler
	ldr x19, [x8]              // x19 := handler->handle_value
	mov x20, x0                // x20 := return value of fun

	ldr x0, [x28, #40]         // current fiber stack to free
	ldr x16, [x8, #24]         // x16 := parent stack
	str x16, [x28, #40]        // restore current_stack = parent
	ldr x26, [x16, #8]         // restore TRAP_PTR = parent->exception_ptr
	ldr x17, [x16]
	mov sp, x17              // restore parent sp

	// Free completed fiber stack
	bl caml_free_stack

	// Apply handle_value to return value
	mov x0, x20
	mov x1, x19
	ldr x16, [x19]
	blr x16

	ldp x21, x22, [sp, #32]
	ldp x19, x20, [sp, #16]
	ldp x29, x30, [sp], #48
	ret

.Lfiber_exn_handler:
	add x8, sp, #32            // x8 := stack_handler
	ldr x19, [x8, #8]          // x19 := handler->handle_exn
	mov x20, x0                // x20 := raised exception

	ldr x0, [x28, #40]
	ldr x16, [x8, #24]
	str x16, [x28, #40]
	ldr x26, [x16, #8]
	ldr x17, [x16]
	mov sp, x17

	bl caml_free_stack

	mov x0, x20
	mov x1, x19
	ldr x16, [x19]
	blr x16

	ldp x21, x22, [sp, #32]
	ldp x19, x20, [sp, #16]
	ldp x29, x30, [sp], #48
	ret
