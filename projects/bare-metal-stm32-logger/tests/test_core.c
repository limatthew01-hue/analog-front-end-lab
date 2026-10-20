#include "logger.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
static unsigned tests;
#define TEST(fn) do { fn(); ++tests; puts(#fn " passed"); } while(0)
static void crc_vector(void) { assert(crc16((const uint8_t *)"123456789",9)==0x29b1); }
static void codec_corruption(void) {
    message_t m={1,65535,0xfedcba98,4095,1234,3300,65535,0x2ff},r;
    uint8_t b[22]; encode_message(&m,b);
    assert(decode_message(b,&r));
    assert(r.sequence==m.sequence && r.tick==m.tick && r.a==m.a && r.b==m.b && r.flags==m.flags);
    for(unsigned i=0;i<22;++i) for(unsigned bit=0;bit<8;++bit) {
        b[i]^=(uint8_t)(1u<<bit); assert(!decode_message(b,&r)); b[i]^=(uint8_t)(1u<<bit);
    }
}
static void parser_resync(void) {
    parser_t p={0}; message_t m={.type=CMD_STATUS,.sequence=55},r;
    uint8_t b[22]; encode_message(&m,b);
    for(unsigned i=0;i<10000;++i) assert(!parser_feed(&p,0x13,i,&r));
    for(unsigned i=0;i<11;++i) assert(!parser_feed(&p,b[i],10001,&r));
    /* A truncated frame followed immediately by a good frame must recover. */
    unsigned count=0;
    for(unsigned i=0;i<22;++i) count+=parser_feed(&p,b[i],10002,&r);
    assert(count==1 && r.sequence==55);
    b[7]^=1;
    for(unsigned i=0;i<22;++i) assert(!parser_feed(&p,b[i],10003,&r));
    b[7]^=1;
    count=0; for(unsigned i=0;i<22;++i) count+=parser_feed(&p,b[i],10004,&r);
    assert(count==1);
}
static void parser_timeout(void) {
    parser_t p={0}; message_t m={.type=CMD_STATUS},r; uint8_t b[22]; encode_message(&m,b);
    for(unsigned i=0;i<10;++i) assert(!parser_feed(&p,b[i],UINT32_MAX-5,&r));
    unsigned count=0;
    for(unsigned i=0;i<22;++i) count+=parser_feed(&p,b[i],25,&r);
    assert(count==1);
}
static void byte_queue_boundaries(void) {
    byte_queue_t q={0}; uint8_t data[256],out;
    for(unsigned i=0;i<256;++i) data[i]=(uint8_t)i;
    assert(!byte_queue_pop(&q,&out));
    for(unsigned cycle=0;cycle<300;++cycle) {
        assert(byte_queue_write(&q,data,256));
        uint16_t head=q.head;
        assert(!byte_queue_write(&q,data,1)); assert(q.head==head);
        for(unsigned i=0;i<256;++i) { assert(byte_queue_pop(&q,&out)); assert(out==data[i]); }
        assert(!byte_queue_pop(&q,&out));
    }
    assert(!byte_queue_write(&q,data,257));
}
static void sample_queue_boundaries(void) {
    sample_queue_t q={0}; sample_t out;
    for(unsigned cycle=0;cycle<40;++cycle) {
        for(unsigned i=0;i<16;++i) assert(sample_queue_push(&q,(sample_t){(uint16_t)i,0,cycle}));
        assert(!sample_queue_push(&q,(sample_t){0}));
        for(unsigned i=0;i<16;++i) { assert(sample_queue_pop(&q,&out)); assert(out.a==i && out.tick==cycle); }
        assert(!sample_queue_pop(&q,&out));
    }
}
static void average_warmup_and_slide(void) {
    app_t app; app_init(&app,0); message_t m;
    for(unsigned i=1;i<=32;++i) {
        app_sample(&app,(sample_t){(uint16_t)(i*10),(uint16_t)(i*20),i*100});
        assert(app_poll(&app,i*100,&m));
        unsigned low=i>16 ? i-15 : 1;
        assert(m.a==5*(low+i) && m.b==10*(low+i));
        assert(!m.flags && m.sequence==i-1);
    }
    app_sample(&app,(sample_t){5000,0,3300});
    assert(app.faults&FAULT_RANGE);
}
static void schedule_wrap_and_stale(void) {
    app_t app; uint32_t start=UINT32_MAX-49; app_init(&app,start); message_t m;
    app_sample(&app,(sample_t){4095,0,25});
    assert(!app_poll(&app,49,&m)); assert(app_poll(&app,50,&m));
    assert(m.a==4095 && !m.flags);
    assert(app_poll(&app,150,&m)); assert(m.flags&FAULT_STALE);
    app_init(&app,0); assert(app_poll(&app,100,&m));
    assert((m.flags&(FAULT_STALE|FLAG_EMPTY))==(FAULT_STALE|FLAG_EMPTY));
    assert(!app_poll(&app,100,&m));
}
static void command_validation(void) {
    app_t app; app_init(&app,0);
    const unsigned periods[]={0,19,20,100,2000,2001,65535};
    for(unsigned i=0;i<sizeof periods/sizeof periods[0];++i) {
        message_t ack=app_command(&app,(message_t){.type=CMD_PERIOD,.a=(uint16_t)periods[i],.sequence=77},10);
        assert(ack.a==(periods[i]<20 || periods[i]>2000)); assert(ack.sequence==77 && ack.b==CMD_PERIOD);
    }
    for(unsigned v=2999;v<=3601;++v) {
        message_t ack=app_command(&app,(message_t){.type=CMD_VREF,.a=(uint16_t)v},0);
        assert(ack.a==(v<3000 || v>3600));
    }
    assert(app_command(&app,(message_t){.type=CMD_STATUS,.a=1},0).a==1);
    assert(app_command(&app,(message_t){.type=CMD_STATUS,.b=1},0).a==1);
    assert(app_command(&app,(message_t){.type=99},0).a==2);
    assert(app_command(&app,(message_t){.type=CMD_STATUS},0).a==0);
}
static void fault_saturation(void) {
    app_t app; app_init(&app,0);
    app_fault(&app,FAULT_DMA,65534); app_fault(&app,FAULT_RX,UINT32_MAX);
    assert(app.dropped==65535 && app.faults==(FAULT_DMA|FAULT_RX));
    app_fault(&app,0,0); assert(app.dropped==65535);
}
int main(void) {
    TEST(crc_vector); TEST(codec_corruption); TEST(parser_resync); TEST(parser_timeout);
    TEST(byte_queue_boundaries); TEST(sample_queue_boundaries); TEST(average_warmup_and_slide);
    TEST(schedule_wrap_and_stale); TEST(command_validation); TEST(fault_saturation);
    printf("%u C test scenarios passed\n",tests);
    message_t m={1,65535,0xfedcba98,4095,1234,3300,65535,0x2ff}; uint8_t b[22]; encode_message(&m,b);
    FILE *f=fopen("build/c-vector.hex","w"); assert(f);
    for(unsigned i=0;i<22;++i) fprintf(f,"%02x",b[i]);
    fputc('\n',f); fclose(f); return 0;
}
