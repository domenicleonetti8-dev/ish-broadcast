#include "BroadcastProbeContract.h"

int broadcast_probe_evaluate(
    bool requested,
    const struct broadcast_probe_evidence *evidence,
    struct broadcast_probe_result *result
) {
    if (!evidence || !result)
        return -1;

    result->registered = false;
    result->findable = false;
    result->connectable = false;
    result->connected = false;

    if ((evidence->a2dp_sink_registered &&
         !evidence->native_a2dp_provider_available) ||
        ((evidence->classic_findable || evidence->classic_connectable) &&
         !evidence->a2dp_sink_registered) ||
        (evidence->inbound_source_connections > 0 &&
         !evidence->a2dp_sink_registered)) {
        result->state = BROADCAST_PROBE_INVALID;
        return -1;
    }

    result->registered = evidence->a2dp_sink_registered;
    result->findable = evidence->a2dp_sink_registered &&
        evidence->classic_findable;
    result->connectable = evidence->a2dp_sink_registered &&
        evidence->classic_connectable;
    result->connected = evidence->a2dp_sink_registered &&
        evidence->inbound_source_connections > 0;

    if (!requested)
        result->state = BROADCAST_PROBE_STOPPED;
    else if (!evidence->native_a2dp_provider_available)
        result->state = BROADCAST_PROBE_PROVIDER_UNAVAILABLE;
    else if (!result->registered)
        result->state = BROADCAST_PROBE_REGISTERING;
    else if (result->connected)
        result->state = BROADCAST_PROBE_CONNECTED;
    else if (result->findable && result->connectable)
        result->state = BROADCAST_PROBE_FINDABLE;
    else
        result->state = BROADCAST_PROBE_REGISTERED;
    return 0;
}

const char *broadcast_probe_state_name(enum broadcast_probe_state state) {
    switch (state) {
        case BROADCAST_PROBE_STOPPED: return "stopped";
        case BROADCAST_PROBE_PROVIDER_UNAVAILABLE:
            return "native_a2dp_provider_unavailable";
        case BROADCAST_PROBE_REGISTERING: return "registering_a2dp_sink";
        case BROADCAST_PROBE_REGISTERED: return "a2dp_sink_registered";
        case BROADCAST_PROBE_FINDABLE: return "findable_and_connectable";
        case BROADCAST_PROBE_CONNECTED: return "source_connected";
        case BROADCAST_PROBE_INVALID: return "invalid_evidence";
    }
    return "invalid_evidence";
}
