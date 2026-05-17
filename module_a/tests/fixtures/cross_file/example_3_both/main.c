static void send_notification(const char *msg) {
    printf("%s\n", msg);
}

notify_t handler;

void run(void) {
    DISPATCH();
    handler("custom");
}
