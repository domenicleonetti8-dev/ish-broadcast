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
    expect_state(input, BROADCAST_HEALTH_BLUETOOTH_UNAVAILABLE,
                 false, false);

    input.bluetooth_ready = true;
    expect_state(input, BROADCAST_HEALTH_CONTROL_SERVICE_PENDING,
                 false, false);

    input.control_service_ready = true;
    expect_state(input, BROADCAST_HEALTH_ADVERTISING_PENDING,
                 false, false);

    input.advertising = true;
    expect_state(input, BROADCAST_HEALTH_AUDIO_ENGINE_OFFLINE,
                 false, false);

    input.audio_engine_running = true;
    expect_state(input, BROADCAST_HEALTH_NO_FINGERS, false, false);

    input.remembered_fingers = 2;
    expect_state(input, BROADCAST_HEALTH_ROUTE_PENDING, false, false);

    input.active_fingers = 1;
    expect_state(input, BROADCAST_HEALTH_ROUTE_PENDING, false, false);

    input.mapped_channels = 2;
    expect_state(input, BROADCAST_HEALTH_READY, true, true);

    input.bluetooth_ready = false;
    expect_state(input, BROADCAST_HEALTH_BLUETOOTH_UNAVAILABLE,
                 false, true);

    struct broadcast_health_result result;
    assert(broadcast_health_evaluate(NULL, &result) == -1);
    assert(broadcast_health_evaluate(&input, NULL) == -1);
    assert(strcmp(broadcast_health_state_name(BROADCAST_HEALTH_INVALID),
                  "invalid") == 0);

    puts("broadcast_health_test: PASS");
    return 0;
}
