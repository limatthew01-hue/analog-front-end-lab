#ifndef LOGGER_H
#define LOGGER_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum { FRAME_BYTES=22, SAMPLE_WINDOW=16, BYTE_CAPACITY=256, SAMPLE_CAPACITY=16 };
enum { MSG_SAMPLE=1, CMD_PERIOD=0x10, CMD_VREF=0x11, CMD_STATUS=0x12, MSG_ACK=0x80 };
enum { FAULT_RANGE=1, FAULT_QUEUE=2, FAULT_DMA=4, FAULT_ADC=8,
       FAULT_RX=16, FAULT_TX=32, FAULT_DMA_LATE=64, FAULT_UART=128,
       FAULT_STALE=256, FLAG_EMPTY=512 };
typedef struct {
    uint8_t type;
    uint16_t sequence;
    uint32_t tick;
    uint16_t a, b, vref, dropped, flags;
} message_t;
typedef struct { uint8_t bytes[FRAME_BYTES], used; uint32_t last_byte; } parser_t;
typedef struct { uint8_t data[BYTE_CAPACITY]; volatile uint16_t head, tail; } byte_queue_t;
typedef struct { uint16_t a, b; uint32_t tick; } sample_t;
typedef struct { sample_t data[SAMPLE_CAPACITY]; volatile uint8_t head, tail; } sample_queue_t;
typedef struct {
    uint16_t window[2][SAMPLE_WINDOW], count, index;
    uint32_t sum[2], last_sample, last_report;
    uint16_t period, vref, sequence, faults, dropped;
} app_t;

uint16_t crc16(const uint8_t *data, size_t length);
void encode_message(const message_t *message, uint8_t bytes[FRAME_BYTES]);
bool decode_message(const uint8_t bytes[FRAME_BYTES], message_t *message);
bool parser_feed(parser_t *parser, uint8_t byte, uint32_t now, message_t *message);
bool byte_queue_write(byte_queue_t *queue, const uint8_t *data, size_t length);
bool byte_queue_pop(byte_queue_t *queue, uint8_t *byte);
bool sample_queue_push(sample_queue_t *queue, sample_t sample);
bool sample_queue_pop(sample_queue_t *queue, sample_t *sample);
void app_init(app_t *app, uint32_t now);
void app_fault(app_t *app, uint16_t flags, uint32_t dropped);
void app_sample(app_t *app, sample_t sample);
bool app_poll(app_t *app, uint32_t now, message_t *message);
message_t app_command(app_t *app, message_t command, uint32_t now);
#endif
