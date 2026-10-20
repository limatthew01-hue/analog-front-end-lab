#include "logger.h"

/* Single-core ISR/main SPSC queues. The compiler barrier publishes payload
 * before the volatile index. These queues are not a multi-thread/SMP API. */
#define BARRIER() __asm__ volatile ("" ::: "memory")
static void put16(uint8_t *p, uint16_t v) { p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static uint16_t get16(const uint8_t *p) { return (uint16_t)(p[0]|((uint16_t)p[1]<<8)); }

uint16_t crc16(const uint8_t *p, size_t n) {
    uint16_t crc=0xffff;
    while(n--) {
        crc ^= (uint16_t)*p++ << 8;
        for(unsigned bit=0; bit<8; ++bit)
            crc=(uint16_t)((crc&0x8000) ? ((uint32_t)crc<<1)^0x1021 : (uint32_t)crc<<1);
    }
    return crc;
}
void encode_message(const message_t *m, uint8_t p[FRAME_BYTES]) {
    p[0]=0xa5; p[1]=0x5a; p[2]=1; p[3]=m->type;
    put16(p+4,m->sequence);
    for(unsigned i=0;i<4;++i) p[6+i]=(uint8_t)(m->tick>>(8*i));
    put16(p+10,m->a); put16(p+12,m->b); put16(p+14,m->vref);
    put16(p+16,m->dropped); put16(p+18,m->flags); put16(p+20,crc16(p,20));
}
bool decode_message(const uint8_t p[FRAME_BYTES], message_t *m) {
    if(p[0]!=0xa5 || p[1]!=0x5a || p[2]!=1 || crc16(p,20)!=get16(p+20)) return false;
    m->type=p[3]; m->sequence=get16(p+4); m->tick=0;
    for(unsigned i=0;i<4;++i) m->tick |= (uint32_t)p[6+i]<<(8*i);
    m->a=get16(p+10); m->b=get16(p+12); m->vref=get16(p+14);
    m->dropped=get16(p+16); m->flags=get16(p+18);
    return true;
}
bool parser_feed(parser_t *p, uint8_t b, uint32_t now, message_t *m) {
    if(p->used && (uint32_t)(now-p->last_byte)>25) p->used=0;
    p->last_byte=now;
    p->bytes[p->used++]=b;
    while(p->used>=2 && (p->bytes[0]!=0xa5 || p->bytes[1]!=0x5a)) {
        for(unsigned i=1;i<p->used;++i) p->bytes[i-1]=p->bytes[i];
        --p->used;
    }
    if(p->used==1 && p->bytes[0]!=0xa5) p->used=0;
    if(p->used<FRAME_BYTES) return false;
    if(decode_message(p->bytes,m)) { p->used=0; return true; }
    for(unsigned i=1;i<FRAME_BYTES;++i) p->bytes[i-1]=p->bytes[i];
    p->used=FRAME_BYTES-1;
    return false;
}
bool byte_queue_write(byte_queue_t *q, const uint8_t *p, size_t n) {
    uint16_t head=q->head;
    if(n>(size_t)(BYTE_CAPACITY-(uint16_t)(head-q->tail))) return false;
    for(size_t i=0;i<n;++i) q->data[(head+i)&(BYTE_CAPACITY-1)]=p[i];
    BARRIER(); q->head=(uint16_t)(head+n); return true;
}
bool byte_queue_pop(byte_queue_t *q, uint8_t *p) {
    uint16_t tail=q->tail;
    if(tail==q->head) return false;
    BARRIER(); *p=q->data[tail&(BYTE_CAPACITY-1)];
    BARRIER(); q->tail=(uint16_t)(tail+1); return true;
}
bool sample_queue_push(sample_queue_t *q, sample_t s) {
    uint8_t head=q->head;
    if((uint8_t)(head-q->tail)>=SAMPLE_CAPACITY) return false;
    q->data[head&(SAMPLE_CAPACITY-1)]=s;
    BARRIER(); q->head=(uint8_t)(head+1); return true;
}
bool sample_queue_pop(sample_queue_t *q, sample_t *s) {
    uint8_t tail=q->tail;
    if(tail==q->head) return false;
    BARRIER(); *s=q->data[tail&(SAMPLE_CAPACITY-1)];
    BARRIER(); q->tail=(uint8_t)(tail+1); return true;
}
void app_init(app_t *app, uint32_t now) {
    *app=(app_t){0}; app->period=100; app->vref=3300;
    app->last_sample=now; app->last_report=now;
}
void app_fault(app_t *app, uint16_t flags, uint32_t dropped) {
    app->faults |= flags;
    app->dropped=(dropped>65535u-app->dropped) ? 65535 : (uint16_t)(app->dropped+dropped);
}
void app_sample(app_t *app, sample_t s) {
    if(s.a>4095 || s.b>4095) { app_fault(app,FAULT_RANGE,1); return; }
    unsigned i=app->index;
    app->sum[0]-=app->window[0][i]; app->sum[1]-=app->window[1][i];
    app->window[0][i]=s.a; app->window[1][i]=s.b;
    app->sum[0]+=s.a; app->sum[1]+=s.b;
    app->index=(uint16_t)((i+1)%SAMPLE_WINDOW);
    if(app->count<SAMPLE_WINDOW) ++app->count;
    app->last_sample=s.tick;
}
bool app_poll(app_t *app, uint32_t now, message_t *m) {
    if((uint32_t)(now-app->last_sample)>50) app->faults |= FAULT_STALE;
    if((uint32_t)(now-app->last_report)<app->period) return false;
    app->last_report=now; /* skip missed reports rather than emitting a burst */
    *m=(message_t){.type=MSG_SAMPLE,.sequence=app->sequence++, .tick=app->last_sample,
        .a=app->count ? (uint16_t)((app->sum[0]+app->count/2)/app->count) : 0,
        .b=app->count ? (uint16_t)((app->sum[1]+app->count/2)/app->count) : 0,
        .vref=app->vref,.dropped=app->dropped,
        .flags=(uint16_t)(app->faults | (app->count ? 0 : FLAG_EMPTY))};
    return true;
}
message_t app_command(app_t *app, message_t c, uint32_t now) {
    uint16_t status=0;
    if(c.b || c.vref || c.dropped || c.flags || c.tick) status=1;
    else if(c.type==CMD_PERIOD) {
        if(c.a<20 || c.a>2000) status=1;
        else { app->period=c.a; app->last_report=now; }
    } else if(c.type==CMD_VREF) {
        if(c.a<3000 || c.a>3600) status=1;
        else app->vref=c.a;
    } else if(c.type==CMD_STATUS) { if(c.a) status=1; }
    else status=2;
    return (message_t){.type=MSG_ACK,.sequence=c.sequence,.tick=now,.a=status,
        .b=c.type,.vref=app->vref,.dropped=app->dropped,.flags=app->faults};
}
