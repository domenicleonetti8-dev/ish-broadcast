#include "BroadcastFingerTable.h"

#include <string.h>

static struct broadcast_finger *find_mutable(
    struct broadcast_finger_table *table,
    const char *identifier
) {
    if (!table || !identifier || !identifier[0])
        return NULL;
    for (size_t i = 0; i < table->count; i++) {
        if (strcmp(table->devices[i].identifier, identifier) == 0)
            return &table->devices[i];
    }
    return NULL;
}

static void copy_text(char *target, size_t size, const char *source) {
    if (!source)
        source = "";
    if (size == 0)
        return;
    strncpy(target, source, size - 1);
    target[size - 1] = '\0';
}

static uint64_t reconnect_delay_ms(unsigned int attempt) {
    uint64_t delay = 500;
    if (attempt > 1) {
        unsigned int shift = attempt - 1;
        if (shift > 6)
            shift = 6;
        delay <<= shift;
    }
    return delay > 30000 ? 30000 : delay;
}

void broadcast_fingers_init(struct broadcast_finger_table *table) {
    if (table)
        memset(table, 0, sizeof(*table));
}

int broadcast_fingers_observe(
    struct broadcast_finger_table *table,
    const char *identifier,
    const char *name
) {
    if (!table || !identifier || !identifier[0])
        return BROADCAST_FINGER_INVALID;
    if (strlen(identifier) >= BROADCAST_DEVICE_ID_SIZE)
        return BROADCAST_FINGER_INVALID;

    struct broadcast_finger *finger = find_mutable(table, identifier);
    if (finger) {
        finger->last_seen_sequence = ++table->sequence;
        if (name && name[0])
            copy_text(finger->name, sizeof(finger->name), name);
        return BROADCAST_FINGER_OK;
    }
    if (table->count < BROADCAST_MAX_DISCOVERED) {
        finger = &table->devices[table->count++];
    } else {
        for (size_t i = 0; i < table->count; i++) {
            struct broadcast_finger *candidate = &table->devices[i];
            if (candidate->wanted)
                continue;
            if (!finger ||
                candidate->last_seen_sequence < finger->last_seen_sequence)
                finger = candidate;
        }
        if (!finger)
            return BROADCAST_FINGER_TABLE_FULL;
        memset(finger, 0, sizeof(*finger));
    }
    copy_text(finger->identifier, sizeof(finger->identifier), identifier);
    copy_text(finger->name, sizeof(finger->name), name ? name : "unknown");
    finger->state = BROADCAST_FINGER_DISCOVERED;
    finger->last_seen_sequence = ++table->sequence;
    return BROADCAST_FINGER_OK;
}

size_t broadcast_fingers_wanted_count(
    const struct broadcast_finger_table *table
) {
    size_t count = 0;
    if (!table)
        return 0;
    for (size_t i = 0; i < table->count; i++)
        if (table->devices[i].wanted)
            count++;
    return count;
}

int broadcast_fingers_bind(
    struct broadcast_finger_table *table,
    const char *identifier
) {
    struct broadcast_finger *finger = find_mutable(table, identifier);
    if (!finger)
        return BROADCAST_FINGER_NOT_FOUND;
    if (!finger->wanted &&
        broadcast_fingers_wanted_count(table) >= BROADCAST_MAX_FINGERS)
        return BROADCAST_FINGER_LIMIT_REACHED;

    if (finger->wanted &&
        (finger->state == BROADCAST_FINGER_CONNECTING ||
         finger->state == BROADCAST_FINGER_BOUND))
        return BROADCAST_FINGER_OK;

    finger->wanted = true;
    finger->state = BROADCAST_FINGER_CONNECTING;
    finger->reconnect_at_ms = 0;
    return BROADCAST_FINGER_OK;
}

int broadcast_fingers_unbind(
    struct broadcast_finger_table *table,
    const char *identifier
) {
    struct broadcast_finger *finger = find_mutable(table, identifier);
    if (!finger)
        return BROADCAST_FINGER_NOT_FOUND;
    finger->wanted = false;
    finger->state = BROADCAST_FINGER_DISCOVERED;
    finger->reconnect_attempts = 0;
    finger->reconnect_at_ms = 0;
    return BROADCAST_FINGER_OK;
}

int broadcast_fingers_connected(
    struct broadcast_finger_table *table,
    const char *identifier
) {
    struct broadcast_finger *finger = find_mutable(table, identifier);
    if (!finger)
        return BROADCAST_FINGER_NOT_FOUND;
    if (!finger->wanted)
        return BROADCAST_FINGER_INVALID;
    finger->state = BROADCAST_FINGER_BOUND;
    finger->reconnect_attempts = 0;
    finger->reconnect_at_ms = 0;
    return BROADCAST_FINGER_OK;
}

static int schedule_reconnect(
    struct broadcast_finger_table *table,
    const char *identifier,
    uint64_t now_ms,
    enum broadcast_finger_state state
) {
    struct broadcast_finger *finger = find_mutable(table, identifier);
    if (!finger)
        return BROADCAST_FINGER_NOT_FOUND;
    if (!finger->wanted) {
        finger->state = BROADCAST_FINGER_DISCOVERED;
        return BROADCAST_FINGER_OK;
    }
    finger->reconnect_attempts++;
    finger->state = state;
    finger->reconnect_at_ms = now_ms +
        reconnect_delay_ms(finger->reconnect_attempts);
    return BROADCAST_FINGER_OK;
}

int broadcast_fingers_disconnected(
    struct broadcast_finger_table *table,
    const char *identifier,
    uint64_t now_ms
) {
    return schedule_reconnect(
        table, identifier, now_ms, BROADCAST_FINGER_RECONNECTING
    );
}

int broadcast_fingers_failed(
    struct broadcast_finger_table *table,
    const char *identifier,
    uint64_t now_ms
) {
    return schedule_reconnect(
        table, identifier, now_ms, BROADCAST_FINGER_ERROR
    );
}

size_t broadcast_fingers_due(
    struct broadcast_finger_table *table,
    uint64_t now_ms,
    const char **identifiers,
    size_t capacity
) {
    size_t count = 0;
    if (!table || !identifiers)
        return 0;
    for (size_t i = 0; i < table->count && count < capacity; i++) {
        struct broadcast_finger *finger = &table->devices[i];
        if (!finger->wanted || finger->reconnect_at_ms == 0 ||
            finger->reconnect_at_ms > now_ms)
            continue;
        identifiers[count++] = finger->identifier;
        finger->state = BROADCAST_FINGER_CONNECTING;
        finger->reconnect_at_ms = 0;
    }
    return count;
}

const struct broadcast_finger *broadcast_fingers_find(
    const struct broadcast_finger_table *table,
    const char *identifier
) {
    return find_mutable((struct broadcast_finger_table *)table, identifier);
}

const char *broadcast_finger_state_name(enum broadcast_finger_state state) {
    switch (state) {
        case BROADCAST_FINGER_DISCOVERED: return "discovered";
        case BROADCAST_FINGER_CONNECTING: return "connecting";
        case BROADCAST_FINGER_BOUND: return "bound";
        case BROADCAST_FINGER_RECONNECTING: return "reconnecting";
        case BROADCAST_FINGER_ERROR: return "error";
    }
    return "unknown";
}
