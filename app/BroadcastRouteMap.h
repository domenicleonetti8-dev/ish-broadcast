#ifndef BROADCAST_ROUTE_MAP_H
#define BROADCAST_ROUTE_MAP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define BROADCAST_ROUTE_MAX_PORTS 32
#define BROADCAST_ROUTE_MAX_SELECTED_PORTS 10
#define BROADCAST_ROUTE_MAX_CHANNELS 64
#define BROADCAST_ROUTE_SILENCE (-1)

struct broadcast_route_map_result {
    size_t destination_channels;
    size_t mapped_channels;
    size_t selected_ports;
    size_t ignored_selected_ports;
};

enum broadcast_route_map_error {
    BROADCAST_ROUTE_MAP_OK = 0,
    BROADCAST_ROUTE_MAP_INVALID = -1,
    BROADCAST_ROUTE_MAP_TOO_MANY_PORTS = -2,
    BROADCAST_ROUTE_MAP_CHANNEL_OVERFLOW = -3,
};

int broadcast_route_map_build(
    const size_t *port_channel_counts,
    const bool *selected_ports,
    size_t port_count,
    size_t source_channel_count,
    int32_t *channel_map,
    size_t channel_map_count,
    struct broadcast_route_map_result *result
);

#endif
