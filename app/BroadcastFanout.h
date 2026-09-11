#ifndef BROADCAST_FANOUT_H
#define BROADCAST_FANOUT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define BROADCAST_FANOUT_MAX_SINKS 10
#define BROADCAST_FANOUT_ID_SIZE 256

typedef long (*broadcast_sink_write_fn)(
    void *context,
    const void *frames,
    size_t frame_count,
    size_t bytes_per_frame
);

struct broadcast_fanout_sink {
    char identifier[BROADCAST_FANOUT_ID_SIZE];
    broadcast_sink_write_fn write;
    void *context;
    bool active;
    uint64_t frames_written;
    uint64_t write_failures;
    long last_result;
};

struct broadcast_fanout {
    struct broadcast_fanout_sink sinks[BROADCAST_FANOUT_MAX_SINKS];
    size_t count;
    uint64_t source_frames;
};

enum broadcast_fanout_result {
    BROADCAST_FANOUT_OK = 0,
    BROADCAST_FANOUT_INVALID = -1,
    BROADCAST_FANOUT_LIMIT_REACHED = -2,
    BROADCAST_FANOUT_NOT_FOUND = -3,
};

void broadcast_fanout_init(struct broadcast_fanout *fanout);
int broadcast_fanout_add(
    struct broadcast_fanout *fanout,
    const char *identifier,
    broadcast_sink_write_fn write,
    void *context
);
int broadcast_fanout_remove(
    struct broadcast_fanout *fanout,
    const char *identifier
);
size_t broadcast_fanout_write(
    struct broadcast_fanout *fanout,
    const void *frames,
    size_t frame_count,
    size_t bytes_per_frame
);
const struct broadcast_fanout_sink *broadcast_fanout_find(
    const struct broadcast_fanout *fanout,
    const char *identifier
);

#endif
