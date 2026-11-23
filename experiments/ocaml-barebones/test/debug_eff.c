#include <stdio.h>
#include <stdint.h>
#include <caml/mlvalues.h>
#include <caml/fiber.h>

void debug_dump_k(value k) {
    printf("[debug_eff] Continuation block at %p: word0=%p, word1=%p\n",
        (void*)k, (void*)Field(k, 0), (void*)Field(k, 1));
}
