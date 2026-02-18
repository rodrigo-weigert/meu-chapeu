#include<opus/opus.h>
#include<stdio.h>
#include<stdlib.h>
#include<stdint.h>

const int SAMPLE_RATE = 48000;
const int SAMPLES_PER_FRAME_PER_CHANNEL = 960;
const int CHANNELS = 2;
const int SAMPLES_PER_FRAME = CHANNELS * SAMPLES_PER_FRAME_PER_CHANNEL;
const int MAX_PACKET_SIZE = 4000;

void free_buffer(void* p) {
    free(p);
}

OpusEncoder* create_encoder() {
    int error;
    OpusEncoder *encoder = opus_encoder_create(SAMPLE_RATE, CHANNELS, OPUS_APPLICATION_AUDIO, &error);
    if (error != OPUS_OK) {
        fprintf(stderr, "Failed to initialize Opus encoder (error code = %d)", error);
        return NULL;
    }
    return encoder;
}

uint8_t* encode(OpusEncoder* encoder, opus_int16* pcm, size_t* out_len) {
    uint8_t* out = (uint8_t*) malloc(sizeof(uint8_t) * MAX_PACKET_SIZE);
    opus_int32 encoded_size = opus_encode(encoder, pcm, SAMPLES_PER_FRAME_PER_CHANNEL, out, MAX_PACKET_SIZE);
    if (encoded_size < 0) {
        fprintf(stderr, "Failed encoding packet (error code %d)", encoded_size);
        free(out);
        return NULL;
    }
    *out_len = encoded_size;
    return out;
}

void destroy_encoder(OpusEncoder* encoder) {
    opus_encoder_destroy(encoder);
}
