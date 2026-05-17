static void do_api_call(const char *name) {
    printf("calling %s\n", name);
}

void run(void) {
    CALL_API("run");
}
