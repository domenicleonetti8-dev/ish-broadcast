#pragma once

#include <stdbool.h>
#include <stddef.h>

enum broadcast_health_state {
    BROADCAST_HEALTH_INVALID = -1,
    BROADCAST_HEALTH_STOPPED = 0,
    BROADCAST_HEALTH_BLUETOOTH_UNAVAILABLE,
    BROADCAST_HEALTH_CONTROL_SERVICE_PENDING,
    BROADCAST_HEALTH_ADVERTISING_PENDING,
    BROADCAST_HEALTH_AUDIO_ENGINE_OFFLINE,
    BROADCAST_HEALTH_NO_FINGERS,
    BROADCAST_HEALTH_ROUTE_PENDING,
    BROADCAST_HEALTH_READY,
};

struct broadcast_health_input {
    bool broadcast_requested;
    bool bluetooth_ready;
    bool control_service_ready;
    bool advertising;
    bool audio_engine_running;
    size_t remembered_fingers;
    size_t active_fingers;
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
