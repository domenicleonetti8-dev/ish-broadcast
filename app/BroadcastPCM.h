#ifndef BROADCAST_PCM_H
#define BROADCAST_PCM_H

#include <stddef.h>

enum broadcast_pcm_result {
    BROADCAST_PCM_OK = 0,
    BROADCAST_PCM_INVALID = -1,
    BROADCAST_PCM_CAPACITY = -2,
};

int broadcast_pcm_s16le_stereo_to_float(
    const void *bytes,
    size_t length,
    float *left,
    float *right,
    size_t frame_capacity,
    size_t *frames_written
);

#endif
