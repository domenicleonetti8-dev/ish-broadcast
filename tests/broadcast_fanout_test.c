#include "app/BroadcastFanout.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct sink_probe {
    uint8_t bytes[128];
    size_t byte_count;
    size_t calls;
    bool fail;
};

static long probe_write(
    void *context,
    const void *frames,
    size_t frame_count,
    size_t bytes_per_frame
) {
    struct sink_probe *probe = context;
    probe->calls++;
    if (probe->fail)
        return -1;
    size_t bytes = frame_count * bytes_per_frame;
    assert(bytes <= sizeof(probe->bytes));
    memcpy(probe->bytes, frames, bytes);
    probe->byte_count = bytes;
    return (long)frame_count;
}

static void test_same_frames_reach_every_sink(void) {
    struct broadcast_fanout fanout;
    struct sink_probe a = {0}, b = {0}, c = {0};
    int16_t frames[] = {1, -2, 3, -4, 5, -6};
    broadcast_fanout_init(&fanout);
    assert(broadcast_fanout_add(&fanout, "a", probe_write, &a) == 0);
    assert(broadcast_fanout_add(&fanout, "b", probe_write, &b) == 0);
    assert(broadcast_fanout_add(&fanout, "c", probe_write, &c) == 0);
    assert(broadcast_fanout_write(&fanout, frames, 3, 4) == 3);
    assert(a.byte_count == sizeof(frames));
    assert(memcmp(a.bytes, frames, sizeof(frames)) == 0);
    assert(memcmp(b.bytes, frames, sizeof(frames)) == 0);
    assert(memcmp(c.bytes, frames, sizeof(frames)) == 0);
}

static void test_failed_sink_does_not_stop_others(void) {
    struct broadcast_fanout fanout;
    struct sink_probe good_a = {0}, failed = {.fail = true}, good_b = {0};
    uint8_t frames[] = {10, 20, 30, 40};
    broadcast_fanout_init(&fanout);
    assert(broadcast_fanout_add(&fanout, "good-a", probe_write, &good_a) == 0);
    assert(broadcast_fanout_add(&fanout, "failed", probe_write, &failed) == 0);
    assert(broadcast_fanout_add(&fanout, "good-b", probe_write, &good_b) == 0);
    assert(broadcast_fanout_write(&fanout, frames, 2, 2) == 2);
    assert(good_a.calls == 1 && good_b.calls == 1 && failed.calls == 1);
    assert(broadcast_fanout_find(&fanout, "failed")->write_failures == 1);
    assert(broadcast_fanout_find(&fanout, "good-a")->frames_written == 2);
    assert(broadcast_fanout_find(&fanout, "good-b")->frames_written == 2);
}

static void test_dynamic_join_and_leave(void) {
    struct broadcast_fanout fanout;
    struct sink_probe a = {0}, b = {0};
    uint8_t frames[] = {1, 2};
    broadcast_fanout_init(&fanout);
    assert(broadcast_fanout_add(&fanout, "a", probe_write, &a) == 0);
    assert(broadcast_fanout_write(&fanout, frames, 2, 1) == 1);
    assert(broadcast_fanout_add(&fanout, "b", probe_write, &b) == 0);
    assert(broadcast_fanout_write(&fanout, frames, 2, 1) == 2);
    assert(a.calls == 2 && b.calls == 1);
    assert(broadcast_fanout_remove(&fanout, "a") == 0);
    assert(broadcast_fanout_write(&fanout, frames, 2, 1) == 1);
    assert(a.calls == 2 && b.calls == 2);
}

static void test_ten_sink_limit(void) {
    struct broadcast_fanout fanout;
    struct sink_probe probes[11] = {0};
    char identifier[16];
    broadcast_fanout_init(&fanout);
    for (int i = 0; i < 10; i++) {
        snprintf(identifier, sizeof(identifier), "sink-%d", i);
        assert(broadcast_fanout_add(
            &fanout, identifier, probe_write, &probes[i]
        ) == 0);
    }
    assert(broadcast_fanout_add(
        &fanout, "sink-10", probe_write, &probes[10]
    ) == BROADCAST_FANOUT_LIMIT_REACHED);

    assert(broadcast_fanout_remove(&fanout, "sink-3") == 0);
    assert(broadcast_fanout_add(
        &fanout, "sink-10", probe_write, &probes[10]
    ) == BROADCAST_FANOUT_OK);
    assert(broadcast_fanout_find(&fanout, "sink-3") == NULL);
    assert(broadcast_fanout_find(&fanout, "sink-10") != NULL);
}

int main(void) {
    test_same_frames_reach_every_sink();
    test_failed_sink_does_not_stop_others();
    test_dynamic_join_and_leave();
    test_ten_sink_limit();
    puts("broadcast_fanout_test: PASS");
    return 0;
}
