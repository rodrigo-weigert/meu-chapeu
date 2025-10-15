#include<opus/opus.h>
#include<stdio.h>
#include<stdlib.h>

const int SAMPLE_RATE = 48000;
const int SAMPLES_PER_FRAME = 960;
const int CHANNELS = 2;
const int INPUT_BUFFER_SIZE = sizeof(opus_int16) * CHANNELS * SAMPLES_PER_FRAME + 10;
const int OUTPUT_BUFFER_SIZE = INPUT_BUFFER_SIZE;

int file_size(FILE* file) {
    int prev = ftell(file), file_size;
    fseek(file, 0L, SEEK_END);
    file_size = ftell(file);
    fseek(file, prev, SEEK_SET);
    return file_size;
}

int total_packets(FILE* file) {
    int bytes_per_frame = SAMPLES_PER_FRAME * CHANNELS * sizeof(opus_int16);
    return (file_size(file) + bytes_per_frame - 1) / bytes_per_frame;
}

unsigned char** get_opus_packets(char* pcm_filename, int* packet_count, int** packet_lengths) {
    int error;
    opus_int16 *input_buf = (opus_int16*) malloc(INPUT_BUFFER_SIZE);
    OpusEncoder *enc = opus_encoder_create(SAMPLE_RATE, CHANNELS, OPUS_APPLICATION_AUDIO, &error);
    FILE* file = fopen(pcm_filename, "rb");
    int fsize = file_size(file);
    int curr_packet = 0;

    *packet_count = total_packets(file);
    *packet_lengths = (int*) malloc(sizeof(int) * (*packet_count));
    unsigned char** output = (unsigned char**) malloc(sizeof(unsigned char*) * (*packet_count));

    //printf("File %s with %d bytes for %d frames\n", pcm_filename, fsize, *packet_count);

    while (!feof(file)) {
       int read = fread(input_buf, sizeof(opus_int16), CHANNELS * SAMPLES_PER_FRAME, file);

       if (read < CHANNELS * SAMPLES_PER_FRAME) {
            for (int i = read; i < CHANNELS * SAMPLES_PER_FRAME; i++) {
                input_buf[i] = 0;
            }
       }
       output[curr_packet] = (unsigned char*) malloc(sizeof(unsigned char) * OUTPUT_BUFFER_SIZE);
       int opus_packet_size = opus_encode(enc, input_buf, SAMPLES_PER_FRAME, output[curr_packet], OUTPUT_BUFFER_SIZE);
       if (error == OPUS_OK) {
           //printf("Read %d values, encoded to %d bytes\n", read, opus_packet_size);
           (*packet_lengths)[curr_packet] = opus_packet_size;
           curr_packet++;
       }
       else {
           fprintf(stderr, "Error code %d in packet %d\n", error, curr_packet-1);
           free(input_buf);
           free(*packet_lengths);
           for (int i = 0; i < curr_packet; i++)
               free(output[i]);
           free(output);
           fclose(file);
           opus_encoder_destroy(enc);
           return NULL;
       }
    }
    
    //printf("Total packets: %d\n", curr_packet);
    free(input_buf);
    fclose(file);
    opus_encoder_destroy(enc);
    return output;
}

int main() {
    int packet_count = 0;
    int* packet_lengths = NULL;

    unsigned char** output = get_opus_packets("out.pcm", &packet_count, &packet_lengths);
    if (output == NULL) {
        fprintf(stderr, "Error\n");
        return -1;
    }
    /*
    printf("Final packet count: %d\n", packet_count);
    printf("Final packet sizes:");
    for (int i = 0; i < packet_count; i++) {
        printf(" %d", packet_lengths[i]);
    }
    printf("\n");

    for (int i = 0; i < packet_count; i++)
    {
        for (int j = 0; j < packet_lengths[i]; j++)
        {
            printf("%d%c", output[i][j], j == packet_lengths[i]-1 ? '\n' : ' ');
        }
    }*/

    free(packet_lengths);
    for (int i = 0; i < packet_count; i++)
        free(output[i]);
    free(output);

    return 0;
}

/*int main() {
    int error;
    opus_int16 *input_buf = (opus_int16*) malloc(INPUT_BUFFER_SIZE);
    OpusEncoder *enc = opus_encoder_create(48000, 2, OPUS_APPLICATION_AUDIO, &error);
    unsigned char* output_buf = (unsigned char*) malloc(OUTPUT_BUFFER_SIZE);
    FILE* file = fopen("out.pcm", "rb");
    int frame_count = total_frames(file);
    int fsize = file_size(file);
    int packet_count = 0;

    printf("File with %d bytes for %d frames\n", fsize, frame_count);

    while (!feof(file)) {
       int read = fread(input_buf, sizeof(opus_int16), CHANNELS * SAMPLES_PER_FRAME, file);

       if (read < CHANNELS * SAMPLES_PER_FRAME) {
            for (int i = read; i < CHANNELS * SAMPLES_PER_FRAME; i++) {
                input_buf[i] = 0;
            }
       }
       int opus_packet_size = opus_encode(enc, input_buf, SAMPLES_PER_FRAME, output_buf, OUTPUT_BUFFER_SIZE);
       if (error == OPUS_OK) {
           printf("Read %d values, encoded to %d bytes\n", read, opus_packet_size);
           packet_count++;
       }
       else {
           printf("Error code %d\n", error);
           free(input_buf);
           free(output_buf);
           fclose(file);
           opus_encoder_destroy(enc);
           return error;
       }
    }
    
    printf("Total packets: %d\n", packet_count);
    free(input_buf);
    free(output_buf);
    fclose(file);
    opus_encoder_destroy(enc);
    return 0;
}*/
