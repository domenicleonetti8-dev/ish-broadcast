#include "app/BroadcastProbeContract.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static struct broadcast_probe_result evaluate(
    bool requested,
    struct broadcast_probe_evidence evidence,
    int expected_result
) {
    struct broadcast_probe_result result = {
        .state = BROADCAST_PROBE_INVALID,
    };
    assert(broadcast_probe_evaluate(requested, &evidence, &result) ==
           expected_result);
    return result;
}

int main(void) {
    assert(strcmp(BROADCAST_PROBE_NAME, "broadcast") == 0);
    assert(BROADCAST_MAX_STRINGS == 10);

    struct broadcast_probe_evidence evidence = {0};
    struct broadcast_probe_result result = evaluate(false, evidence, 0);
    assert(result.state == BROADCAST_PROBE_STOPPED);

    // A BLE name is a control-plane signal, never classic speaker evidence.
    evidence.ble_gatt_advertising = true;
    result = evaluate(true, evidence, 0);
    assert(result.state == BROADCAST_PROBE_PROVIDER_UNAVAILABLE);
    assert(!result.registered && !result.findable && !result.connectable);

    evidence.native_a2dp_provider_available = true;
    result = evaluate(true, evidence, 0);
    assert(result.state == BROADCAST_PROBE_REGISTERING);

    evidence.a2dp_sink_registered = true;
    result = evaluate(true, evidence, 0);
    assert(result.state == BROADCAST_PROBE_REGISTERED);

    evidence.classic_findable = true;
    evidence.classic_connectable = true;
    result = evaluate(true, evidence, 0);
    assert(result.state == BROADCAST_PROBE_FINDABLE);
    assert(result.registered && result.findable && result.connectable);

    evidence.inbound_source_connections = 1;
    result = evaluate(true, evidence, 0);
    assert(result.state == BROADCAST_PROBE_CONNECTED);
    assert(result.connected);

    struct broadcast_probe_evidence impossible = {
        .a2dp_sink_registered = true,
    };
    result = evaluate(true, impossible, -1);
    assert(result.state == BROADCAST_PROBE_INVALID);

    impossible = (struct broadcast_probe_evidence){
        .native_a2dp_provider_available = true,
        .classic_findable = true,
    };
    result = evaluate(true, impossible, -1);
    assert(result.state == BROADCAST_PROBE_INVALID);

    assert(broadcast_probe_evaluate(true, NULL, &result) == -1);
    assert(broadcast_probe_evaluate(true, &evidence, NULL) == -1);
    assert(strcmp(broadcast_probe_state_name(BROADCAST_PROBE_INVALID),
                  "invalid_evidence") == 0);

    puts("broadcast_probe_contract_test: PASS");
    return 0;
}
