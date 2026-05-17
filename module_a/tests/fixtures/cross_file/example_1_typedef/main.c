static void my_func(int x) { (void)x; }

callback_t handler;

void init(void) {
    handler = my_func;
    handler(42);
}
