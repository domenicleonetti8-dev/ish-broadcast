#include "app/BroadcastRouteMap.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static uint32_t next_random(uint32_t *state) {
    *state = *state * 1664525u + 1013904223u;
    return *state;
}

int main(void) {
    uint32_t random = 0xB16B00B5u;
    size_t counts[12];
    bool selected[12];
    int32_t map[24];
    struct broadcast_route_map_result result;

    for (size_t step = 0; step < 100000; step++) {
        size_t portCount = 1 + next_random(&random) % 12;
        size_t channelCount = 0;
        for (size_t port = 0; port < portCount; port++) {
            counts[port] = 1 + next_random(&random) % 2;
            selected[port] = (next_random(&random) & 1u) != 0;
            channelCount += counts[port];
        }

        assert(broadcast_route_map_build(
            counts,
            selected,
            portCount,
            2,
            map,
            channelCount,
            &result
        ) == BROADCAST_ROUTE_MAP_OK);
        assert(result.selected_ports <= 10);
        assert(result.destination_channels == channelCount);

        size_t offset = 0;
        size_t accepted = 0;
        size_t mapped = 0;
        for (size_t port = 0; port < portCount; port++) {
            bool shouldMap = selected[port] && accepted < 10;
            if (shouldMap)
                accepted++;
            for (size_t channel = 0; channel < counts[port]; channel++) {
                if (shouldMap) {
                    assert(map[offset + channel] ==
                        (int32_t)(channel % 2));
                    mapped++;
                } else {
                    assert(map[offset + channel] == -1);
                }
            }
            offset += counts[port];
        }
        assert(result.mapped_channels == mapped);
    }

    puts("broadcast_route_stress_test: PASS (100000 route rebuilds)");
    return 0;
}
