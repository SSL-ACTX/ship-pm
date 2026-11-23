#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>

#define CAML_INTERNALS
#define NATIVE_CODE

#include <caml/misc.h>
#include <caml/mlvalues.h>
#include <caml/gc.h>
#include <caml/domain_state.h>
#include <caml/fiber.h>

#define MINOR_HEAP_SIZE (4 * 1024 * 1024) /* 4 MB */
static uint8_t minor_heap_buf[MINOR_HEAP_SIZE] __attribute__((aligned(16)));

#define C_STACK_SIZE (1 * 1024 * 1024) /* 1 MB */
static uint8_t c_stack_buf[C_STACK_SIZE] __attribute__((aligned(16)));

#define MAIN_STACK_WORDS 4096
static uint8_t main_stack_buf[sizeof(struct stack_info) + (MAIN_STACK_WORDS * sizeof(value)) + sizeof(struct stack_handler) + 64] __attribute__((aligned(16)));

caml_domain_state micro_domain_state;

void caml_initialize(value *loc, value val) {
    *loc = val;
}

void caml_modify(value *loc, value val) {
    *loc = val;
}

void caml_call_gc(void) {
    fprintf(stderr, "[micro_runtime] OOM: Minor heap bump buffer exhausted!\n");
    abort();
}

void caml_call_realloc_stack(void) {
    /* Stack reallocation stub */
}

void caml_free_stack(struct stack_info *stk) {
    free(stk);
}

/* Comparisons */
value caml_equal(value v1, value v2) { return Val_bool(v1 == v2); }
value caml_notequal(value v1, value v2) { return Val_bool(v1 != v2); }
value caml_lessthan(value v1, value v2) { return Val_bool(v1 < v2); }
value caml_greaterthan(value v1, value v2) { return Val_bool(v1 > v2); }
value caml_lessequal(value v1, value v2) { return Val_bool(v1 <= v2); }
value caml_greaterequal(value v1, value v2) { return Val_bool(v1 >= v2); }

/* Currying and tuplifying */
value caml_curry2(value f, value arg1, value arg2) {
    typedef value (*fn2)(value, value, value);
    return ((fn2)(((void**)f)[2]))(arg1, arg2, f);
}

value caml_curry3(value f, value arg1, value arg2, value arg3) {
    typedef value (*fn3)(value, value, value, value);
    return ((fn3)(((void**)f)[2]))(arg1, arg2, arg3, f);
}

value caml_tuplify2(value tuple, value clos) {
    typedef value (*fn2)(value, value, value);
    value fst = Field(tuple, 0);
    value snd = Field(tuple, 1);
    return ((fn2)(((void**)clos)[2]))(fst, snd, clos);
}

/* Object / Extension identifiers */
static uintnat oo_counter = 0;
value caml_fresh_oo_id(value unit) {
    oo_counter++;
    return Val_int(oo_counter);
}

/* Allocation stubs are implemented in alloc_arm64.s */

/* Weak symbol entry hooks for arbitrary modules */
__attribute__((weak)) void caml_user_entry(void) {}
__attribute__((weak)) value caml_user_test(value unit) { return Val_int(0); }

extern void call_ocaml_init(void (*fn)(void), void *domain_ptr, void *young_ptr);
extern value call_ocaml_func(value (*fn)(value), void *domain_ptr, void *young_ptr, value arg);

extern void camlNano_entry(void) __asm__("camlNano.entry");

void micro_runtime_init(void) {
    micro_domain_state.young_start = (value*)minor_heap_buf;
    micro_domain_state.young_end = (value*)(minor_heap_buf + MINOR_HEAP_SIZE);
    micro_domain_state.young_ptr = micro_domain_state.young_end;
    micro_domain_state.young_limit = (atomic_uintnat)micro_domain_state.young_start;
    micro_domain_state.c_stack = (struct c_stack_link*)(c_stack_buf + C_STACK_SIZE - 64);

    struct stack_info *stk = (struct stack_info*)main_stack_buf;
    uintptr_t high = ((uintptr_t)main_stack_buf + sizeof(struct stack_info) + (MAIN_STACK_WORDS * sizeof(value)) + 15) & ~15ULL;
    struct stack_handler *hand = (struct stack_handler*)high;
    stk->handler = hand;
    hand->parent = NULL;
    stk->sp = (void*)hand;
    stk->exception_ptr = NULL;
    micro_domain_state.current_stack = stk;

    call_ocaml_init(camlNano_entry, &micro_domain_state, micro_domain_state.young_end);
}

int main(int argc, char **argv) {
    micro_runtime_init();
    call_ocaml_init(caml_user_entry, &micro_domain_state, micro_domain_state.young_end);
    value res = call_ocaml_func(caml_user_test, &micro_domain_state, micro_domain_state.young_end, Val_unit);
    printf("[micro_runtime] Result: %ld\n", (long)Long_val(res));
    return 0;
}
