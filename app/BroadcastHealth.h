#pragma once

#include <stdbool.h>
#include <stddef.h>

enum broadcast_health_state {
    BROADCAST_HEALTH_INVALID = -1,
    BROADCAST_HEALTH_STOPPED = 0,
    BROADCAST_HEALTH_A2DP_SINK_UNAVAILABLE,
    BROADCAST_HEALTH_A2DP_SINK_REGISTRATION_PENDING,
    BROADCAST_HEALTH_A2DP_SINK_DISCOVERABILITY_PENDING,
    BROADCAST_HEALTH_INBOUND_CONNECTION_PENDING,
    BROADCAST_HEALTH_NO_STRINGS,
    BROADCAST_HEALTH_STRING_ROUTE_PENDING,
    BROADCAST_HEALTH_READY,
};

struct broadcast_health_input {
    bool broadcast_requested;
    bool a2dp_sink_provider_available;
    bool a2dp_sink_registered;
    bool probe_findable;
    bool probe_connectable;
    bool inbound_source_connected;
    bool audio_engine_running;
    size_t remembered_strings;
    size_t active_strings;
    size_t mapped_channels;
};

struct broadcast_health_result {
    enum broadcast_health_state state;
    bool ready;
    bool can_run_audio_probe;
};

int broadcast_health_evaluate(
    const struct broadcast_health_input *input,
    struct broadcast_health_result *result
);

const char *broadcast_health_state_name(enum broadcast_health_state state);
const char *broadcast_health_action(enum broadcast_health_state state);
