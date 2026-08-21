#ifndef BROADCAST_PROBE_CONTRACT_H
#define BROADCAST_PROBE_CONTRACT_H

#include <stdbool.h>
#include <stddef.h>

#define BROADCAST_PROBE_NAME "broadcast"
#define BROADCAST_MAX_STRINGS 10

enum broadcast_probe_state {
    BROADCAST_PROBE_INVALID = -1,
    BROADCAST_PROBE_STOPPED = 0,
    BROADCAST_PROBE_PROVIDER_UNAVAILABLE,
    BROADCAST_PROBE_REGISTERING,
    BROADCAST_PROBE_REGISTERED,
    BROADCAST_PROBE_FINDABLE,
    BROADCAST_PROBE_CONNECTED,
};

struct broadcast_probe_evidence {
    bool native_a2dp_provider_available;
    bool a2dp_sink_registered;
    bool classic_findable;
    bool classic_connectable;
    size_t inbound_source_connections;
    bool ble_gatt_advertising;
};

struct broadcast_probe_result {
    enum broadcast_probe_state state;
    bool registered;
    bool findable;
    bool connectable;
    bool connected;
};

int broadcast_probe_evaluate(
    bool requested,
    const struct broadcast_probe_evidence *evidence,
    struct broadcast_probe_result *result
);

const char *broadcast_probe_state_name(enum broadcast_probe_state state);

#endif
