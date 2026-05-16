#include "include/api.h"
#include <stdlib.h>

static driver_ctx_t *global_ctx = NULL;

int driver_setup(void) {
    global_ctx = (driver_ctx_t *)malloc(sizeof(driver_ctx_t));
    if (!global_ctx) return -1;
    global_ctx->ops = &my_ops;
    global_ctx->priv = NULL;
    driver_register(&my_ops);
    return 0;
}

void driver_teardown(void) {
    if (global_ctx) {
        free(global_ctx);
        global_ctx = NULL;
    }
}

int driver_do_work(const char *input) {
    if (!global_ctx || !input) return -1;
    return driver_process_data(global_ctx, input, 5);
}
