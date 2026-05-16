#include <stdio.h>

#define CALL_DEBUG() debug_log(__func__)

static void debug_log(const char *msg) {
    fprintf(stderr, "%s\n", msg);
}

void do_work(void) {
    CALL_DEBUG();
    int x = 0;
    (void)x;
}
