#include "app/BroadcastHealth.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void expect_state(
    struct broadcast_health_input input,
    enum broadcast_health_state expected,
    bool ready,
    bool can_probe
) {
    struct broadcast_health_result result;
    assert(broadcast_health_evaluate(&input, &result) == 0);
    assert(result.state == expected);
    assert(result.ready == ready);
    assert(result.can_run_audio_probe == can_probe);
    assert(strlen(broadcast_health_state_name(result.state)) > 0);
    assert(strlen(broadcast_health_action(result.state)) > 0);
}

int main(void) {
    struct broadcast_health_input input = {0};
    expect_state(input, BROADCAST_HEALTH_STOPPED, false, false);

    input.broadcast_requested = true;
    expect_state(input, BROADCAST_HEALTH_A2DP_SINK_UNAVAILABLE,
                 false, false);

    input.a2dp_sink_provider_available = true;
    expect_state(input, BROADCAST_HEALTH_A2DP_SINK_REGISTRATION_PENDING,
                 false, false);

    input.a2dp_sink_registered = true;
    expect_state(input, BROADCAST_HEALTH_A2DP_SINK_DISCOVERABILITY_PENDING,
                 false, false);

    input.probe_findable = true;
    expect_state(input, BROADCAST_HEALTH_A2DP_SINK_DISCOVERABILITY_PENDING,
                 false, false);

    input.probe_connectable = true;
    expect_state(input, BROADCAST_HEALTH_INBOUND_CONNECTION_PENDING,
                 false, false);

    input.inbound_source_connected = true;
    expect_state(input, BROADCAST_HEALTH_NO_STRINGS, false, false);

    input.remembered_strings = 2;
    expect_state(input, BROADCAST_HEALTH_STRING_ROUTE_PENDING,
                 false, false);

    input.audio_engine_running = true;
    input.active_strings = 1;
    expect_state(input, BROADCAST_HEALTH_STRING_ROUTE_PENDING,
                 false, false);

    input.mapped_channels = 2;
    expect_state(input, BROADCAST_HEALTH_READY, true, true);

    input.a2dp_sink_provider_available = false;
    expect_state(input, BROADCAST_HEALTH_A2DP_SINK_UNAVAILABLE,
                 false, true);

    struct broadcast_health_result result;
    assert(broadcast_health_evaluate(NULL, &result) == -1);
    assert(broadcast_health_evaluate(&input, NULL) == -1);
    assert(strcmp(broadcast_health_state_name(BROADCAST_HEALTH_INVALID),
                  "invalid") == 0);

    puts("broadcast_health_test: PASS");
    return 0;
}
