#include "BroadcastHealth.h"

int broadcast_health_evaluate(
    const struct broadcast_health_input *input,
    struct broadcast_health_result *result
) {
    if (!input || !result)
        return -1;

    result->ready = false;
    result->can_run_audio_probe = input->audio_engine_running &&
        input->active_strings > 0 && input->mapped_channels > 0;

    if (!input->broadcast_requested)
        result->state = BROADCAST_HEALTH_STOPPED;
    else if (!input->a2dp_sink_provider_available)
        result->state = BROADCAST_HEALTH_A2DP_SINK_UNAVAILABLE;
    else if (!input->a2dp_sink_registered)
        result->state = BROADCAST_HEALTH_A2DP_SINK_REGISTRATION_PENDING;
    else if (!input->probe_findable || !input->probe_connectable)
        result->state = BROADCAST_HEALTH_A2DP_SINK_DISCOVERABILITY_PENDING;
    else if (!input->inbound_source_connected)
        result->state = BROADCAST_HEALTH_INBOUND_CONNECTION_PENDING;
    else if (input->remembered_strings == 0)
        result->state = BROADCAST_HEALTH_NO_STRINGS;
    else if (!input->audio_engine_running || input->active_strings == 0 ||
             input->mapped_channels == 0)
        result->state = BROADCAST_HEALTH_STRING_ROUTE_PENDING;
    else {
        result->state = BROADCAST_HEALTH_READY;
        result->ready = true;
    }
    return 0;
}

const char *broadcast_health_state_name(enum broadcast_health_state state) {
    switch (state) {
        case BROADCAST_HEALTH_STOPPED: return "stopped";
        case BROADCAST_HEALTH_A2DP_SINK_UNAVAILABLE:
            return "a2dp_sink_provider_unavailable";
        case BROADCAST_HEALTH_A2DP_SINK_REGISTRATION_PENDING:
            return "a2dp_sink_registration_pending";
        case BROADCAST_HEALTH_A2DP_SINK_DISCOVERABILITY_PENDING:
            return "probe_discoverability_pending";
        case BROADCAST_HEALTH_INBOUND_CONNECTION_PENDING:
            return "inbound_source_pending";
        case BROADCAST_HEALTH_NO_STRINGS: return "no_strings";
        case BROADCAST_HEALTH_STRING_ROUTE_PENDING:
            return "string_route_pending";
        case BROADCAST_HEALTH_READY: return "ready_for_listening_test";
        case BROADCAST_HEALTH_INVALID: return "invalid";
    }
    return "invalid";
}

const char *broadcast_health_action(enum broadcast_health_state state) {
    switch (state) {
        case BROADCAST_HEALTH_STOPPED:
            return "Tap Start.";
        case BROADCAST_HEALTH_A2DP_SINK_UNAVAILABLE:
            return "A native A2DP-sink provider is required; stock iOS does not expose one to apps.";
        case BROADCAST_HEALTH_A2DP_SINK_REGISTRATION_PENDING:
            return "Register broadcast as a classic Bluetooth A2DP speaker.";
        case BROADCAST_HEALTH_A2DP_SINK_DISCOVERABILITY_PENDING:
            return "Make the broadcast speaker probe findable and connectable.";
        case BROADCAST_HEALTH_INBOUND_CONNECTION_PENDING:
            return "Connect an audio source to the broadcast speaker probe.";
        case BROADCAST_HEALTH_NO_STRINGS:
            return "Attach at least one outbound Bluetooth speaker string.";
        case BROADCAST_HEALTH_STRING_ROUTE_PENDING:
            return "Reconnect a string and wait for its physical audio route.";
        case BROADCAST_HEALTH_READY:
            return "Run Check, then Test Sound for physical confirmation.";
        case BROADCAST_HEALTH_INVALID:
            return "Restart broadcast and run the check again.";
    }
    return "Restart broadcast and run the check again.";
}
