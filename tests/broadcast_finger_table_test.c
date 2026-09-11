#include "app/BroadcastFingerTable.h"

#include <assert.h>
#include <stdio.h>

static void observe_devices(struct broadcast_finger_table *table, int count) {
    char identifier[32];
    char name[32];
    for (int i = 0; i < count; i++) {
        snprintf(identifier, sizeof(identifier), "device-%02d", i);
        snprintf(name, sizeof(name), "speaker-%02d", i);
        assert(broadcast_fingers_observe(table, identifier, name) == 0);
    }
}

static void test_capacity_and_independence(void) {
    struct broadcast_finger_table table;
    broadcast_fingers_init(&table);
    observe_devices(&table, 12);

    char identifier[32];
    for (int i = 0; i < BROADCAST_MAX_FINGERS; i++) {
        snprintf(identifier, sizeof(identifier), "device-%02d", i);
        assert(broadcast_fingers_bind(&table, identifier) == 0);
        assert(broadcast_fingers_connected(&table, identifier) == 0);
    }
    assert(broadcast_fingers_wanted_count(&table) == 10);
    assert(broadcast_fingers_bind(&table, "device-10") ==
        BROADCAST_FINGER_LIMIT_REACHED);

    assert(broadcast_fingers_disconnected(&table, "device-03", 1000) == 0);
    assert(broadcast_fingers_find(&table, "device-03")->state ==
        BROADCAST_FINGER_RECONNECTING);
    assert(broadcast_fingers_find(&table, "device-04")->state ==
        BROADCAST_FINGER_BOUND);
    assert(broadcast_fingers_find(&table, "device-09")->state ==
        BROADCAST_FINGER_BOUND);
}

static void test_reconnect_and_recovery(void) {
    struct broadcast_finger_table table;
    const char *due[BROADCAST_MAX_FINGERS];
    broadcast_fingers_init(&table);
    assert(broadcast_fingers_observe(&table, "speaker-a", "OKKO") == 0);
    assert(broadcast_fingers_bind(&table, "speaker-a") == 0);
    assert(broadcast_fingers_connected(&table, "speaker-a") == 0);
    assert(broadcast_fingers_failed(&table, "speaker-a", 2000) == 0);
    assert(broadcast_fingers_due(&table, 2499, due, 10) == 0);
    assert(broadcast_fingers_due(&table, 2500, due, 10) == 1);
    assert(broadcast_fingers_find(&table, "speaker-a")->state ==
        BROADCAST_FINGER_CONNECTING);
    assert(broadcast_fingers_connected(&table, "speaker-a") == 0);
    assert(broadcast_fingers_find(&table, "speaker-a")->state ==
        BROADCAST_FINGER_BOUND);
}

static void test_unbind_cancels_reconnect(void) {
    struct broadcast_finger_table table;
    const char *due[BROADCAST_MAX_FINGERS];
    broadcast_fingers_init(&table);
    assert(broadcast_fingers_observe(&table, "speaker-b", "ISB284") == 0);
    assert(broadcast_fingers_bind(&table, "speaker-b") == 0);
    assert(broadcast_fingers_disconnected(&table, "speaker-b", 1000) == 0);
    assert(broadcast_fingers_unbind(&table, "speaker-b") == 0);
    assert(broadcast_fingers_due(&table, 60000, due, 10) == 0);
    assert(broadcast_fingers_wanted_count(&table) == 0);
}

static void test_duplicate_discovery_updates_name(void) {
    struct broadcast_finger_table table;
    broadcast_fingers_init(&table);
    assert(broadcast_fingers_observe(&table, "speaker-c", "unknown") == 0);
    assert(broadcast_fingers_observe(&table, "speaker-c", "AR Charleston") == 0);
    assert(table.count == 1);
    assert(broadcast_fingers_find(&table, "speaker-c") != NULL);
}

static void test_idempotent_bind_and_backoff(void) {
    struct broadcast_finger_table table;
    const char *due[1];
    broadcast_fingers_init(&table);
    assert(broadcast_fingers_observe(&table, "speaker-d", "speaker") == 0);
    assert(broadcast_fingers_bind(&table, "speaker-d") == 0);
    assert(broadcast_fingers_bind(&table, "speaker-d") == 0);
    assert(broadcast_fingers_wanted_count(&table) == 1);

    assert(broadcast_fingers_failed(&table, "speaker-d", 1000) == 0);
    assert(broadcast_fingers_due(&table, 1500, due, 1) == 1);
    assert(broadcast_fingers_failed(&table, "speaker-d", 1500) == 0);
    assert(broadcast_fingers_due(&table, 2499, due, 1) == 0);
    assert(broadcast_fingers_due(&table, 2500, due, 1) == 1);
}

static void test_discovery_table_boundary(void) {
    struct broadcast_finger_table table;
    char identifier[32];
    broadcast_fingers_init(&table);
    observe_devices(&table, BROADCAST_MAX_DISCOVERED);
    snprintf(identifier, sizeof(identifier), "device-%02d", BROADCAST_MAX_DISCOVERED);
    assert(broadcast_fingers_observe(&table, identifier, "replacement") ==
        BROADCAST_FINGER_OK);
    assert(table.count == BROADCAST_MAX_DISCOVERED);
    assert(broadcast_fingers_find(&table, "device-00") == NULL);
    assert(broadcast_fingers_find(&table, identifier) != NULL);
}

static void test_invalid_operations(void) {
    struct broadcast_finger_table table;
    broadcast_fingers_init(&table);
    assert(broadcast_fingers_bind(&table, "missing") ==
        BROADCAST_FINGER_NOT_FOUND);
    assert(broadcast_fingers_observe(&table, "", "bad") ==
        BROADCAST_FINGER_INVALID);
    assert(broadcast_fingers_connected(&table, "missing") ==
        BROADCAST_FINGER_NOT_FOUND);
}

static void test_long_audio_route_uid(void) {
    struct broadcast_finger_table table;
    const char *identifier =
        "BluetoothHFP:00000000-1111-2222-3333-444444444444:"
        "manufacturer-route-instance-abcdefghijklmnopqrstuvwxyz-0123456789";
    broadcast_fingers_init(&table);
    assert(broadcast_fingers_observe(
        &table, identifier, "Long route UID"
    ) == BROADCAST_FINGER_OK);
    assert(broadcast_fingers_find(&table, identifier) != NULL);
    assert(broadcast_fingers_bind(&table, identifier) ==
        BROADCAST_FINGER_OK);

    char tooLong[BROADCAST_DEVICE_ID_SIZE + 1];
    for (size_t i = 0; i < sizeof(tooLong) - 1; i++)
        tooLong[i] = 'x';
    tooLong[sizeof(tooLong) - 1] = '\0';
    assert(broadcast_fingers_observe(&table, tooLong, "invalid") ==
        BROADCAST_FINGER_INVALID);
}

int main(void) {
    test_capacity_and_independence();
    test_reconnect_and_recovery();
    test_unbind_cancels_reconnect();
    test_duplicate_discovery_updates_name();
    test_idempotent_bind_and_backoff();
    test_discovery_table_boundary();
    test_invalid_operations();
    test_long_audio_route_uid();
    puts("broadcast_string_registry_test: PASS");
    return 0;
}
