#include "app/BroadcastRouteMap.h"

#include <assert.h>
#include <stdio.h>

static void test_duplicates_stereo_to_every_selected_port(void) {
    size_t counts[] = {2, 2, 1};
    bool selected[] = {true, true, true};
    int32_t map[5];
    struct broadcast_route_map_result result;

    assert(broadcast_route_map_build(
        counts, selected, 3, 2, map, 5, &result
    ) == BROADCAST_ROUTE_MAP_OK);
    assert(map[0] == 0 && map[1] == 1);
    assert(map[2] == 0 && map[3] == 1);
    assert(map[4] == 0);
    assert(result.selected_ports == 3);
    assert(result.mapped_channels == 5);
}

static void test_unselected_port_is_silent(void) {
    size_t counts[] = {2, 2, 2};
    bool selected[] = {true, false, true};
    int32_t map[8];
    struct broadcast_route_map_result result;

    assert(broadcast_route_map_build(
        counts, selected, 3, 2, map, 8, &result
    ) == BROADCAST_ROUTE_MAP_OK);
    assert(map[0] == 0 && map[1] == 1);
    assert(map[2] == -1 && map[3] == -1);
    assert(map[4] == 0 && map[5] == 1);
    assert(map[6] == -1 && map[7] == -1);
}

static void test_ten_finger_limit_keeps_other_channels_silent(void) {
    size_t counts[12];
    bool selected[12];
    int32_t map[24];
    struct broadcast_route_map_result result;

    for (size_t i = 0; i < 12; i++) {
        counts[i] = 2;
        selected[i] = true;
    }
    assert(broadcast_route_map_build(
        counts, selected, 12, 2, map, 24, &result
    ) == BROADCAST_ROUTE_MAP_OK);
    assert(result.selected_ports == 10);
    assert(result.ignored_selected_ports == 2);
    for (size_t i = 0; i < 20; i++)
        assert(map[i] == (int32_t)(i % 2));
    for (size_t i = 20; i < 24; i++)
        assert(map[i] == -1);
}

static void test_route_join_and_leave_rebuilds_offsets(void) {
    size_t before_counts[] = {2, 2};
    bool before_selected[] = {false, true};
    int32_t before[4];
    size_t after_counts[] = {2};
    bool after_selected[] = {true};
    int32_t after[2];
    struct broadcast_route_map_result result;

    assert(broadcast_route_map_build(
        before_counts, before_selected, 2, 2, before, 4, &result
    ) == BROADCAST_ROUTE_MAP_OK);
    assert(before[0] == -1 && before[1] == -1);
    assert(before[2] == 0 && before[3] == 1);

    assert(broadcast_route_map_build(
        after_counts, after_selected, 1, 2, after, 2, &result
    ) == BROADCAST_ROUTE_MAP_OK);
    assert(after[0] == 0 && after[1] == 1);
}

static void test_rejects_channel_overflow(void) {
    size_t counts[] = {2, 3};
    bool selected[] = {true, true};
    int32_t map[4];
    struct broadcast_route_map_result result;
    assert(broadcast_route_map_build(
        counts, selected, 2, 2, map, 4, &result
    ) == BROADCAST_ROUTE_MAP_CHANNEL_OVERFLOW);
}

int main(void) {
    test_duplicates_stereo_to_every_selected_port();
    test_unselected_port_is_silent();
    test_ten_finger_limit_keeps_other_channels_silent();
    test_route_join_and_leave_rebuilds_offsets();
    test_rejects_channel_overflow();
    puts("broadcast_route_map_test: PASS");
    return 0;
}
