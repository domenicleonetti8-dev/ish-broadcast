#include "app/BroadcastPCM.h"

#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>

static void assert_close(float actual, float expected) {
    assert(fabsf(actual - expected) < 0.000001f);
}

static void test_exact_samples_and_unaligned_input(void) {
    uint8_t storage[] = {
        0xff,
        0x00, 0x00, 0x00, 0x00,
        0xff, 0x7f, 0x00, 0x80,
        0x00, 0xc0, 0x00, 0x40,
    };
    float left[3] = {0};
    float right[3] = {0};
    size_t frames = 0;
    assert(broadcast_pcm_s16le_stereo_to_float(
        storage + 1, 12, left, right, 3, &frames
    ) == BROADCAST_PCM_OK);
    assert(frames == 3);
    assert_close(left[0], 0.0f);
    assert_close(right[0], 0.0f);
    assert_close(left[1], 32767.0f / 32768.0f);
    assert_close(right[1], -1.0f);
    assert_close(left[2], -0.5f);
    assert_close(right[2], 0.5f);
}

static void test_validation(void) {
    uint8_t bytes[8] = {0};
    float left[2] = {0};
    float right[2] = {0};
    size_t frames = 99;
    assert(broadcast_pcm_s16le_stereo_to_float(
        NULL, 8, left, right, 2, &frames
    ) == BROADCAST_PCM_INVALID);
    assert(frames == 0);
    frames = 99;
    assert(broadcast_pcm_s16le_stereo_to_float(
        bytes, 0, left, right, 2, &frames
    ) == BROADCAST_PCM_INVALID);
    assert(frames == 0);
    frames = 99;
    assert(broadcast_pcm_s16le_stereo_to_float(
        bytes, 7, left, right, 2, &frames
    ) == BROADCAST_PCM_INVALID);
    assert(frames == 0);
    frames = 99;
    assert(broadcast_pcm_s16le_stereo_to_float(
        bytes, 8, left, right, 1, &frames
    ) == BROADCAST_PCM_CAPACITY);
    assert(frames == 0);
    assert(broadcast_pcm_s16le_stereo_to_float(
        bytes, 8, left, right, 2, NULL
    ) == BROADCAST_PCM_INVALID);
}

int main(void) {
    test_exact_samples_and_unaligned_input();
    test_validation();
    puts("broadcast_pcm_test: PASS");
    return 0;
}
