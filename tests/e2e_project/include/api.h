#ifndef API_H
#define API_H

typedef struct {
    int (*init)(void *ctx);
    int (*process)(void *ctx, const char *data, int len);
    void (*cleanup)(void *ctx);
} driver_ops_t;

typedef struct {
    driver_ops_t *ops;
    void *priv;
} driver_ctx_t;

int driver_register(driver_ops_t *ops);
int driver_process_data(driver_ctx_t *ctx, const char *data, int len);

#endif
