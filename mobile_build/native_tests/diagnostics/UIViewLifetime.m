/* Diagnostic-only native observer. Never linked into normal application builds. */
#include <objc/runtime.h>
#include <objc/message.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stdatomic.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static void (*original_dealloc)(id, SEL);
static int trace_fd = -1;
static _Atomic uint64_t reserved_bytes;
static _Atomic int limit_reported;
static const uint64_t trace_limit = 64 * 1024 * 1024;

static char *text(char *out, const char *value, size_t limit) {
    for (size_t i = 0; value && value[i] && i < limit; i++) *out++ = value[i];
    return out;
}
static char *hex(char *out, uintptr_t value) {
    static const char digits[] = "0123456789abcdef";
    *out++ = '0'; *out++ = 'x';
    for (int shift = (int)(sizeof(value) * 8) - 4; shift >= 0; shift -= 4)
        *out++ = digits[(value >> shift) & 15];
    return out;
}
static void record(char kind, uintptr_t object, const char *class_name) {
    char buffer[384], *end = buffer;
    uint64_t thread = 0;
    struct timespec now;
    pthread_threadid_np(NULL, &thread);
    clock_gettime(CLOCK_MONOTONIC, &now);
    *end++ = kind; *end++ = ' ';
    end = hex(end, (uintptr_t)getpid()); *end++ = ' ';
    end = hex(end, object); *end++ = ' ';
    end = hex(end, (uintptr_t)thread); *end++ = ' ';
    end = hex(end, (uintptr_t)now.tv_sec); *end++ = ' ';
    end = hex(end, (uintptr_t)now.tv_nsec); *end++ = ' ';
    end = text(end, class_name, 160); *end++ = '\n';
    size_t length = (size_t)(end - buffer);
    uint64_t offset = atomic_fetch_add_explicit(&reserved_bytes, length, memory_order_relaxed);
    if (trace_fd >= 0 && offset + length <= trace_limit) {
        /* One write per bounded record. Short/error writes remain incomplete
           evidence; never throw, allocate, retry an effect or skip original IMP. */
        (void)write(trace_fd, buffer, length);
    } else if (trace_fd >= 0 && !atomic_exchange_explicit(&limit_reported, 1, memory_order_relaxed)) {
        static const char exhausted[] = "T trace-budget-exhausted\n";
        (void)write(trace_fd, exhausted, sizeof(exhausted) - 1);
    }
}
static void traced_dealloc(id object, SEL selector) {
    uintptr_t address = (uintptr_t)object;
    record('E', address, ""); /* Before even reading the object's class. */
    record('C', address, class_getName(object_getClass(object)));
    original_dealloc(object, selector);
    record('X', address, ""); /* Saved integer only; object is already dead. */
}
__attribute__((constructor)) static void install_trace(void) {
    const char *path = getenv("LOGISTICS_DEALLOC_TRACE_PATH");
    if (!path || !path[0]) return;
    trace_fd = open(path, O_WRONLY | O_APPEND | O_CLOEXEC | O_NOFOLLOW);
    if (trace_fd < 0) return;
    Class view = objc_getClass("UIView");
    Method method = class_getInstanceMethod(view, sel_registerName("dealloc"));
    char result[8] = {0}, instance[32] = {0}, selector[8] = {0};
    if (!method) { record('F', 0, "missing-method"); return; }
    method_getReturnType(method, result, sizeof(result));
    method_getArgumentType(method, 0, instance, sizeof(instance));
    method_getArgumentType(method, 1, selector, sizeof(selector));
    if (method_getNumberOfArguments(method) != 2 || strcmp(result, "v") ||
        strcmp(instance, "@") || strcmp(selector, ":")) {
        record('F', 0, "unexpected-method-encoding"); return;
    }
    original_dealloc = (void (*)(id, SEL))method_getImplementation(method);
    if (!original_dealloc) { record('F', 0, "missing-original-imp"); return; }
    IMP previous = method_setImplementation(method, (IMP)traced_dealloc);
    if (previous != (IMP)original_dealloc) {
        method_setImplementation(method, previous);
        record('F', 0, "concurrent-implementation-change"); return;
    }
    record('I', (uintptr_t)original_dealloc, "UIView.dealloc-installed-v1");
    record('N', 0, getenv("MallocStackLoggingNoCompact"));
    record('G', 0, getenv("MallocStackLogging"));
    (void)fsync(trace_fd);
}
