#include <stdio.h>
#include <stdint.h>
#include <caml/mlvalues.h>

void debug_apply3_entry(value a1, value a2, value a3, value clos) {
    printf("[debug_apply3]\n");
    printf("  a1 (eff)   = %p\n", (void*)a1);
    printf("  a2 (k)     = %p\n", (void*)a2);
    printf("  a3 (last_f)= %p\n", (void*)a3);
    printf("  clos       = %p\n", (void*)clos);
    if (clos) {
        printf("  clos header: %p, word0 (code ptr)=%p, word1 (arity)=%p\n",
               (void*)Hd_val(clos), (void*)Field(clos, 0), (void*)Field(clos, 1));
    }
}
