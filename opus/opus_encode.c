#include<assert.h>
#include<opus/opus.h>
#include<stdio.h>
#include<stdlib.h>
#include<stdint.h>

const int SAMPLE_RATE = 48000;
const int SAMPLES_PER_FRAME_PER_CHANNEL = 960;
const int CHANNELS = 2;
const int SAMPLES_PER_FRAME = CHANNELS * SAMPLES_PER_FRAME_PER_CHANNEL;
const int MAX_PACKET_SIZE = 4000;

size_t file_size(FILE* file) {
    int prev = ftell(file), file_size;
    fseek(file, 0L, SEEK_END);
    file_size = ftell(file);
    fseek(file, prev, SEEK_SET);
    return file_size;
}

void free_buffer(void* p) {
    free(p);
}

/**
 * Reads the entire PCM file into a buffer.
 * Pads with zeros so the last opus frame has the correct number of samples.
 */
opus_int16* read_pcm(char* filename, size_t* out_sample_count) {
    FILE* file = fopen(filename, "rb");
    size_t size_in_bytes = file_size(file);

    assert(size_in_bytes % sizeof(opus_int16) == 0);

    size_t sample_count = size_in_bytes / sizeof(opus_int16);

    size_t padded_sample_count = sample_count;
    if (sample_count % SAMPLES_PER_FRAME != 0) {
        padded_sample_count += SAMPLES_PER_FRAME - (sample_count % SAMPLES_PER_FRAME);
    }

    opus_int16* data = (opus_int16*) calloc(padded_sample_count, sizeof(opus_int16));

    if (data == NULL) {
        return NULL;
    }

    size_t read = fread(data, sizeof(opus_int16), sample_count, file);
    fclose(file);

    if (read == sample_count) {
        *out_sample_count = padded_sample_count;
        return data;
    }

    *out_sample_count = 0;
    free(data);
    return NULL;
}

uint8_t* get_opus_packets(char* pcm_filename, size_t* packet_count, size_t** packet_lengths) {
    size_t sample_count;
    opus_int16 *samples = read_pcm(pcm_filename, &sample_count);

    if (samples == NULL) {
        fprintf(stderr, "Failed to read file %s", pcm_filename);
        return NULL;
    }

    assert(sample_count % SAMPLES_PER_FRAME == 0);

    size_t num_packets = sample_count / SAMPLES_PER_FRAME;

    int error;
    OpusEncoder *encoder = opus_encoder_create(SAMPLE_RATE, CHANNELS, OPUS_APPLICATION_AUDIO, &error);

    if (error != OPUS_OK) {
        fprintf(stderr, "Failed to initialize Opus encoder (error code = %d)", error);
        free(samples);
        return NULL;
    }

    size_t* lengths = (size_t*) malloc(sizeof(size_t) * num_packets);
    uint8_t* output = (uint8_t*) malloc(sizeof(uint8_t) * num_packets * MAX_PACKET_SIZE);
    opus_int32 bytes_written = 0;

    for (size_t i = 0; i < num_packets; i++) {
        opus_int32 packet_size = opus_encode(encoder, samples + i * SAMPLES_PER_FRAME, SAMPLES_PER_FRAME_PER_CHANNEL, output + bytes_written, MAX_PACKET_SIZE);
        if (packet_size >= 0) {
            lengths[i] = packet_size;
            bytes_written += packet_size;
        }
        else {
           fprintf(stderr, "Error code %d in packet %ld\n", packet_size, i);
           free(samples);
           free(lengths);
           free(output);
           opus_encoder_destroy(encoder);
           return NULL;
        }
    }

    *packet_lengths = lengths;
    *packet_count = num_packets;

    free(samples);
    opus_encoder_destroy(encoder);
    return output;
}

int main(int argc, char* argv[]) {
    size_t packet_count = 0;
    size_t* packet_lengths = NULL;

    if (argc < 2) {
        fprintf(stderr, "Missing file argument\n");
        return 1;
    }

    uint8_t* output = get_opus_packets(argv[1], &packet_count, &packet_lengths);
    if (output == NULL) {
        fprintf(stderr, "Opus encoding failed\n");
        return -1;
    }

    size_t total_bytes = 0;

    for (size_t i = 0; i < packet_count; i++) {
        total_bytes += packet_lengths[i];
    }

    printf("Final packet count: %ld\n", packet_count);
    printf("Total compressed bytes: %ld\n", total_bytes);

    free(packet_lengths);
    free(output);
    return 0;
}
