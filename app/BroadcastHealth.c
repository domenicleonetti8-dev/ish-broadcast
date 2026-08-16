#include "BroadcastHealth.h"

int broadcast_health_evaluate(
    const struct broadcast_health_input *input,
    struct broadcast_health_result *result
) {
    if (!input || !result)
        return -1;

    result->ready = false;
    result->can_run_audio_probe = input->audio_engine_running &&
        input->active_fingers > 0 && input->mapped_channels > 0;

    if (!input->broadcast_requested)
        result->state = BROADCAST_HEALTH_STOPPED;
    else if (!input->bluetooth_ready)
        result->state = BROADCAST_HEALTH_BLUETOOTH_UNAVAILABLE;
    else if (!input->control_service_ready)
        result->state = BROADCAST_HEALTH_CONTROL_SERVICE_PENDING;
    else if (!input->advertising)
        result->state = BROADCAST_HEALTH_ADVERTISING_PENDING;
    else if (!input->audio_engine_running)
        result->state = BROADCAST_HEALTH_AUDIO_ENGINE_OFFLINE;
    else if (input->remembered_fingers == 0)
        result->state = BROADCAST_HEALTH_NO_FINGERS;
    else if (input->active_fingers == 0 || input->mapped_channels == 0)
        result->state = BROADCAST_HEALTH_ROUTE_PENDING;
    else {
        result->state = BROADCAST_HEALTH_READY;
        result->ready = true;
    }
    return 0;
}

const char *broadcast_health_state_name(enum broadcast_health_state state) {
    switch (state) {
        case BROADCAST_HEALTH_STOPPED: return "stopped";
        case BROADCAST_HEALTH_BLUETOOTH_UNAVAILABLE:
            return "bluetooth_unavailable";
        case BROADCAST_HEALTH_CONTROL_SERVICE_PENDING:
            return "control_service_pending";
        case BROADCAST_HEALTH_ADVERTISING_PENDING:
            return "advertising_pending";
        case BROADCAST_HEALTH_AUDIO_ENGINE_OFFLINE:
            return "audio_engine_offline";
        case BROADCAST_HEALTH_NO_FINGERS: return "no_fingers";
        case BROADCAST_HEALTH_ROUTE_PENDING: return "route_pending";
        case BROADCAST_HEALTH_READY: return "ready_for_listening_test";
        case BROADCAST_HEALTH_INVALID: return "invalid";
    }
    return "invalid";
}

const char *broadcast_health_action(enum broadcast_health_state state) {
    switch (state) {
        case BROADCAST_HEALTH_STOPPED:
            return "Tap Start.";
        case BROADCAST_HEALTH_BLUETOOTH_UNAVAILABLE:
            return "Turn on Bluetooth and allow access for broadcast.";
        case BROADCAST_HEALTH_CONTROL_SERVICE_PENDING:
            return "Wait for the broadcast control service to become ready.";
        case BROADCAST_HEALTH_ADVERTISING_PENDING:
            return "Wait for the broadcast name to begin advertising.";
        case BROADCAST_HEALTH_AUDIO_ENGINE_OFFLINE:
            return "Tap Retry to restart the audio engine.";
        case BROADCAST_HEALTH_NO_FINGERS:
            return "Choose a Bluetooth audio output, then bind its finger.";
        case BROADCAST_HEALTH_ROUTE_PENDING:
            return "Reconnect a remembered output or choose it again.";
        case BROADCAST_HEALTH_READY:
            return "Run Check, then Test Sound for physical confirmation.";
        case BROADCAST_HEALTH_INVALID:
            return "Restart broadcast and run the check again.";
    }
    return "Restart broadcast and run the check again.";
}
