#include "app/BroadcastFanout.h"
#include "app/BroadcastFingerTable.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>

struct probe {
    uint64_t writes;
    bool fail;
};

static long write_probe(
    void *context,
    const void *frames,
    size_t frame_count,
    size_t bytes_per_frame
) {
    struct probe *probe = context;
    (void)frames;
    (void)bytes_per_frame;
    probe->writes++;
    return probe->fail ? -1 : (long)frame_count;
}

static uint32_t next_random(uint32_t *state) {
    *state = *state * 1664525u + 1013904223u;
    return *state;
}

static void assert_invariants(
    const struct broadcast_finger_table *fingers,
    const struct broadcast_fanout *fanout
) {
    assert(fingers->count <= BROADCAST_MAX_DISCOVERED);
    assert(broadcast_fingers_wanted_count(fingers) <= BROADCAST_MAX_FINGERS);
    for (size_t i = 0; i < fingers->count; i++) {
        const struct broadcast_finger *finger = &fingers->devices[i];
        if (finger->state == BROADCAST_FINGER_BOUND)
            assert(finger->wanted);
        if (!finger->wanted)
            assert(finger->reconnect_at_ms == 0);
    }
    assert(fanout->count <= BROADCAST_FANOUT_MAX_SINKS);
    size_t active = 0;
    for (size_t i = 0; i < fanout->count; i++)
        if (fanout->sinks[i].active)
            active++;
    assert(active <= BROADCAST_FANOUT_MAX_SINKS);
}

int main(void) {
    struct broadcast_finger_table fingers;
    struct broadcast_fanout fanout;
    struct probe probes[48] = {0};
    const char *due[BROADCAST_MAX_FINGERS];
    uint32_t random = 0xBADC0DEu;
    uint64_t now = 0;
    uint8_t frames[32] = {0};
    char identifier[32];

    broadcast_fingers_init(&fingers);
    broadcast_fanout_init(&fanout);

    for (unsigned int step = 0; step < 100000; step++) {
        uint32_t value = next_random(&random);
        unsigned int device = value % 48;
        unsigned int operation = (value >> 8) % 9;
        snprintf(identifier, sizeof(identifier), "device-%02u", device);
        now += value % 7;

        switch (operation) {
            case 0:
                broadcast_fingers_observe(&fingers, identifier, "speaker");
                break;
            case 1:
                broadcast_fingers_bind(&fingers, identifier);
                break;
            case 2:
                broadcast_fingers_connected(&fingers, identifier);
                break;
            case 3:
                broadcast_fingers_disconnected(&fingers, identifier, now);
                break;
            case 4:
                broadcast_fingers_unbind(&fingers, identifier);
                broadcast_fanout_remove(&fanout, identifier);
                break;
            case 5:
                broadcast_fingers_due(
                    &fingers, now, due, BROADCAST_MAX_FINGERS
                );
                break;
            case 6:
                broadcast_fanout_add(
                    &fanout, identifier, write_probe, &probes[device]
                );
                break;
            case 7:
                probes[device].fail = !probes[device].fail;
                broadcast_fanout_write(&fanout, frames, 8, 4);
                break;
            case 8:
                broadcast_fingers_failed(&fingers, identifier, now);
                break;
        }
        assert_invariants(&fingers, &fanout);
    }

    puts("broadcast_string_stress_test: PASS (100000 operations)");
    return 0;
}
