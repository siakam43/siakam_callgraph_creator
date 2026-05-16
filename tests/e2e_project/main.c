#include "include/api.h"
#include <stdio.h>

int driver_setup(void);
void driver_teardown(void);
int driver_do_work(const char *input);

typedef int (*work_fn)(const char *);
static work_fn g_worker = NULL;

void set_worker(work_fn fn) {
    g_worker = fn;
}

int execute_work(const char *data) {
    if (g_worker) {
        return g_worker(data);
    }
    return -1;
}

int main(void) {
    driver_setup();
    set_worker(driver_do_work);
    int result = execute_work("test data");
    printf("Result: %d\n", result);
    driver_teardown();
    return result;
}
