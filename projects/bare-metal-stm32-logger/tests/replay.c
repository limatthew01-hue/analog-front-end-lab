#include "logger.h"
#include <stdio.h>
int main(void) {
    app_t app; app_init(&app,0); unsigned t,a,b;
    while(scanf("%u,%u,%u",&t,&a,&b)==3) {
        app_sample(&app,(sample_t){(uint16_t)a,(uint16_t)b,t}); message_t m;
        if(app_poll(&app,t,&m)) {
            uint8_t bytes[FRAME_BYTES]; encode_message(&m,bytes);
            for(unsigned i=0;i<FRAME_BYTES;++i) printf("%02x",bytes[i]);
            putchar('\n');
        }
    }
    return 0;
}
