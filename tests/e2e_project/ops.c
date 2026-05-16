#include "include/api.h"

static int my_driver_init(void *ctx) { return 0; }
static int my_driver_process(void *ctx, const char *data, int len) {
    (void)data; (void)len;
    return len;
}
static void my_driver_cleanup(void *ctx) {}

static driver_ops_t my_ops = {
    .init = my_driver_init,
    .process = my_driver_process,
    .cleanup = my_driver_cleanup,
};

int driver_register(driver_ops_t *ops) {
    (void)ops;
    return 0;
}

int driver_process_data(driver_ctx_t *ctx, const char *data, int len) {
    if (ctx && ctx->ops && ctx->ops->process) {
        return ctx->ops->process(ctx->priv, data, len);
    }
    return -1;
}
