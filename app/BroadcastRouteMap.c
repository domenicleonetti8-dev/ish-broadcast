#include "BroadcastRouteMap.h"

#include <string.h>

int broadcast_route_map_build(
    const size_t *port_channel_counts,
    const bool *selected_ports,
    size_t port_count,
    size_t source_channel_count,
    int32_t *channel_map,
    size_t channel_map_count,
    struct broadcast_route_map_result *result
) {
    if (!port_channel_counts || !selected_ports || !channel_map ||
        !result || source_channel_count == 0 || channel_map_count == 0)
        return BROADCAST_ROUTE_MAP_INVALID;
    if (port_count > BROADCAST_ROUTE_MAX_PORTS)
        return BROADCAST_ROUTE_MAP_TOO_MANY_PORTS;
    if (channel_map_count > BROADCAST_ROUTE_MAX_CHANNELS)
        return BROADCAST_ROUTE_MAP_CHANNEL_OVERFLOW;

    for (size_t i = 0; i < channel_map_count; i++)
        channel_map[i] = BROADCAST_ROUTE_SILENCE;
    memset(result, 0, sizeof(*result));
    result->destination_channels = channel_map_count;

    size_t output_offset = 0;
    for (size_t port = 0; port < port_count; port++) {
        size_t channels = port_channel_counts[port];
        if (channels > channel_map_count - output_offset)
            return BROADCAST_ROUTE_MAP_CHANNEL_OVERFLOW;

        bool selected = selected_ports[port];
        if (selected &&
            result->selected_ports >= BROADCAST_ROUTE_MAX_SELECTED_PORTS) {
            selected = false;
            result->ignored_selected_ports++;
        }
        if (selected)
            result->selected_ports++;

        for (size_t channel = 0; channel < channels; channel++) {
            if (selected) {
                channel_map[output_offset + channel] =
                    (int32_t)(channel % source_channel_count);
                result->mapped_channels++;
            }
        }
        output_offset += channels;
    }
    return BROADCAST_ROUTE_MAP_OK;
}
