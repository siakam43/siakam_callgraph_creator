#include <stdio.h>

#define LOG_AND_SEND(msg) do { log(msg); send(msg); } while(0)

static void log(const char *msg) {
    fprintf(stderr, "%s\n", msg);
}

static void send(const char *msg) {
    transmit(msg);
}

void do_work(void) {
    LOG_AND_SEND("hello");
}
