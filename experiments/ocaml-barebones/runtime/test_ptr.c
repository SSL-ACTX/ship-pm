#include <stdio.h>
#include <caml/mlvalues.h>
#include <caml/fiber.h>

int main() {
    printf("sizeof(struct stack_info) = %zu\n", sizeof(struct stack_info));
    printf("offsetof(struct stack_info, handler) = %zu\n", offsetof(struct stack_info, handler));
    printf("sizeof(struct stack_handler) = %zu\n", sizeof(struct stack_handler));
    printf("offsetof(struct stack_handler, parent) = %zu\n", offsetof(struct stack_handler, parent));
    return 0;
}
