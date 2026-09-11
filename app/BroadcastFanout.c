#include "BroadcastFanout.h"

#include <string.h>

static struct broadcast_fanout_sink *find_mutable(
    struct broadcast_fanout *fanout,
    const char *identifier
) {
    if (!fanout || !identifier || !identifier[0])
        return NULL;
    for (size_t i = 0; i < fanout->count; i++) {
        if (strcmp(fanout->sinks[i].identifier, identifier) == 0)
            return &fanout->sinks[i];
    }
    return NULL;
}

void broadcast_fanout_init(struct broadcast_fanout *fanout) {
    if (fanout)
        memset(fanout, 0, sizeof(*fanout));
}

int broadcast_fanout_add(
    struct broadcast_fanout *fanout,
    const char *identifier,
    broadcast_sink_write_fn write,
    void *context
) {
    if (!fanout || !identifier || !identifier[0] || !write ||
        strlen(identifier) >= BROADCAST_FANOUT_ID_SIZE)
        return BROADCAST_FANOUT_INVALID;

    struct broadcast_fanout_sink *sink = find_mutable(fanout, identifier);
    if (sink) {
        sink->write = write;
        sink->context = context;
        sink->active = true;
        return BROADCAST_FANOUT_OK;
    }
    for (size_t i = 0; i < fanout->count; i++) {
        if (!fanout->sinks[i].active) {
            sink = &fanout->sinks[i];
            memset(sink, 0, sizeof(*sink));
            break;
        }
    }
    if (!sink) {
        if (fanout->count >= BROADCAST_FANOUT_MAX_SINKS)
            return BROADCAST_FANOUT_LIMIT_REACHED;
        sink = &fanout->sinks[fanout->count++];
    }
    strncpy(sink->identifier, identifier, sizeof(sink->identifier) - 1);
    sink->identifier[sizeof(sink->identifier) - 1] = '\0';
    sink->write = write;
    sink->context = context;
    sink->active = true;
    return BROADCAST_FANOUT_OK;
}

int broadcast_fanout_remove(
    struct broadcast_fanout *fanout,
    const char *identifier
) {
    struct broadcast_fanout_sink *sink = find_mutable(fanout, identifier);
    if (!sink)
        return BROADCAST_FANOUT_NOT_FOUND;
    sink->active = false;
    sink->write = NULL;
    sink->context = NULL;
    return BROADCAST_FANOUT_OK;
}

size_t broadcast_fanout_write(
    struct broadcast_fanout *fanout,
    const void *frames,
    size_t frame_count,
    size_t bytes_per_frame
) {
    if (!fanout || (!frames && frame_count) || bytes_per_frame == 0)
        return 0;

    fanout->source_frames += frame_count;
    size_t successful = 0;
    for (size_t i = 0; i < fanout->count; i++) {
        struct broadcast_fanout_sink *sink = &fanout->sinks[i];
        if (!sink->active || !sink->write)
            continue;
        long result = sink->write(
            sink->context, frames, frame_count, bytes_per_frame
        );
        sink->last_result = result;
        if (result == (long)frame_count) {
            sink->frames_written += frame_count;
            successful++;
        } else {
            sink->write_failures++;
        }
    }
    return successful;
}

const struct broadcast_fanout_sink *broadcast_fanout_find(
    const struct broadcast_fanout *fanout,
    const char *identifier
) {
    return find_mutable((struct broadcast_fanout *)fanout, identifier);
}
