#include <stdint.h>
typedef intptr_t value;
#define Val_unit 1

extern void camlNano_effects_entry(void) __asm__("camlNano_effects.entry");
extern void camlEffect_demo_entry(void) __asm__("camlEffect_demo.entry");
extern value camlEffect_demo_run(value) __asm__("camlEffect_demo.run_47");

void caml_user_entry(void) {
    camlNano_effects_entry();
    camlEffect_demo_entry();
}

value caml_user_test(value unit) {
    return camlEffect_demo_run(Val_unit);
}
