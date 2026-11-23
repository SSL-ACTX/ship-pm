#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define CAML_INTERNALS
#define NATIVE_CODE

#include <caml/misc.h>
#include <caml/mlvalues.h>
#include <caml/domain_state.h>
#include <caml/fiber.h>

#define FIBER_STACK_WORDS 1024

value caml_alloc_stack(value hval, value hexn, value heff) {
    size_t total_size = sizeof(struct stack_info) + (FIBER_STACK_WORDS * sizeof(value)) + sizeof(struct stack_handler) + 64;
    void *mem = malloc(total_size);
    if (!mem) {
        fprintf(stderr, "[effects_runtime] OOM allocating fiber stack\n");
        abort();
    }
    memset(mem, 0, total_size);

    struct stack_info *stack = (struct stack_info*)mem;
    uintptr_t high = ((uintptr_t)mem + sizeof(struct stack_info) + (FIBER_STACK_WORDS * sizeof(value)) + 15) & ~15ULL;
    struct stack_handler *hand = (struct stack_handler*)high;

    stack->handler = hand;
    hand->handle_value = hval;
    hand->handle_exn = hexn;
    hand->handle_effect = heff;
    hand->parent = NULL;

    stack->sp = (void*)hand;
    stack->exception_ptr = NULL;

    return Val_ptr(stack);
}

value caml_continuation_use_noexc(value cont) {
    value *stk_ptr = (value*)cont;
    value stk = *stk_ptr;
    *stk_ptr = Val_unit;
    return stk;
}

void caml_raise_continuation_already_resumed(void) {
    fprintf(stderr, "[effects_runtime] Error: Continuation already resumed\n");
    abort();
}

void caml_raise_unhandled_effect(value effect) {
    fprintf(stderr, "[effects_runtime] Error: Unhandled effect\n");
    abort();
}
