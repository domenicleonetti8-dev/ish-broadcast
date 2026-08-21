#include "BroadcastPCM.h"

#include <stdint.h>

static int32_t decode_s16le(const uint8_t *bytes) {
    uint16_t value = (uint16_t)bytes[0] |
        ((uint16_t)bytes[1] << 8);
    return value <= INT16_MAX
        ? (int32_t)value
        : (int32_t)value - 65536;
}

int broadcast_pcm_s16le_stereo_to_float(
    const void *bytes,
    size_t length,
    float *left,
    float *right,
    size_t frame_capacity,
    size_t *frames_written
) {
    if (!frames_written)
        return BROADCAST_PCM_INVALID;
    *frames_written = 0;
    if (!bytes || !left || !right || length == 0 || length % 4 != 0)
        return BROADCAST_PCM_INVALID;

    size_t frame_count = length / 4;
    if (frame_count > frame_capacity)
        return BROADCAST_PCM_CAPACITY;

    const uint8_t *input = bytes;
    const float scale = 1.0f / 32768.0f;
    for (size_t frame = 0; frame < frame_count; frame++) {
        size_t offset = frame * 4;
        left[frame] = (float)decode_s16le(&input[offset]) * scale;
        right[frame] = (float)decode_s16le(&input[offset + 2]) * scale;
    }
    *frames_written = frame_count;
    return BROADCAST_PCM_OK;
}
