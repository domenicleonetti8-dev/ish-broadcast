#ifndef BROADCAST_FINGER_TABLE_H
#define BROADCAST_FINGER_TABLE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define BROADCAST_MAX_FINGERS 10
#define BROADCAST_MAX_DISCOVERED 32
#define BROADCAST_DEVICE_ID_SIZE 256
#define BROADCAST_DEVICE_NAME_SIZE 128

enum broadcast_finger_state {
    BROADCAST_FINGER_DISCOVERED = 0,
    BROADCAST_FINGER_CONNECTING,
    BROADCAST_FINGER_BOUND,
    BROADCAST_FINGER_RECONNECTING,
    BROADCAST_FINGER_ERROR,
};

struct broadcast_finger {
    char identifier[BROADCAST_DEVICE_ID_SIZE];
    char name[BROADCAST_DEVICE_NAME_SIZE];
    enum broadcast_finger_state state;
    bool wanted;
    unsigned int reconnect_attempts;
    uint64_t reconnect_at_ms;
    uint64_t last_seen_sequence;
};

struct broadcast_finger_table {
    struct broadcast_finger devices[BROADCAST_MAX_DISCOVERED];
    size_t count;
    uint64_t sequence;
};

enum broadcast_finger_result {
    BROADCAST_FINGER_OK = 0,
    BROADCAST_FINGER_NOT_FOUND = -1,
    BROADCAST_FINGER_LIMIT_REACHED = -2,
    BROADCAST_FINGER_TABLE_FULL = -3,
    BROADCAST_FINGER_INVALID = -4,
};

void broadcast_fingers_init(struct broadcast_finger_table *table);
int broadcast_fingers_observe(
    struct broadcast_finger_table *table,
    const char *identifier,
    const char *name
);
int broadcast_fingers_bind(
    struct broadcast_finger_table *table,
    const char *identifier
);
int broadcast_fingers_unbind(
    struct broadcast_finger_table *table,
    const char *identifier
);
int broadcast_fingers_connected(
    struct broadcast_finger_table *table,
    const char *identifier
);
int broadcast_fingers_disconnected(
    struct broadcast_finger_table *table,
    const char *identifier,
    uint64_t now_ms
);
int broadcast_fingers_failed(
    struct broadcast_finger_table *table,
    const char *identifier,
    uint64_t now_ms
);
size_t broadcast_fingers_due(
    struct broadcast_finger_table *table,
    uint64_t now_ms,
    const char **identifiers,
    size_t capacity
);
size_t broadcast_fingers_wanted_count(
    const struct broadcast_finger_table *table
);
const struct broadcast_finger *broadcast_fingers_find(
    const struct broadcast_finger_table *table,
    const char *identifier
);
const char *broadcast_finger_state_name(enum broadcast_finger_state state);

#endif
