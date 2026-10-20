/* Register offsets and trigger/DMA mappings: ST RM0368 rev 6.
 * Target: NUCLEO-F401RE only; no HAL, RTOS, PLL or external crystal. */
#include "logger.h"
#include <stdatomic.h>
#define REG(address) (*(volatile uint32_t *)(uintptr_t)(address))
#define RCC 0x40023800u
#define GPIOA 0x40020000u
#define ADC1 0x40012000u
#define DMA2 0x40026400u
#define STREAM (DMA2+0x10u)
#define TIM2 0x40000000u
#define UART2 0x40004400u
static volatile uint32_t ticks;
static volatile uint16_t adc_data[4] __attribute__((aligned(4)));
static sample_queue_t samples;
static byte_queue_t rx,tx;
static atomic_uint pending_faults, pending_drops;
static app_t app;

static void fault(unsigned flags, unsigned dropped) {
    atomic_fetch_or_explicit(&pending_faults,flags,memory_order_relaxed);
    atomic_fetch_add_explicit(&pending_drops,dropped,memory_order_relaxed);
}
static void nvic(unsigned irq, unsigned priority) {
    ((volatile uint8_t *)0xe000e400u)[irq]=(uint8_t)(priority<<4);
    REG(0xe000e100u+4*(irq/32))=1u<<(irq%32);
}
static void acquisition_stop(void) {
    REG(TIM2)&=~1u; REG(ADC1+8)&=~1u; REG(STREAM)&=~1u;
}
void SysTick_Handler(void) { ++ticks; }
void DMA2_Stream0_IRQHandler(void) {
    uint32_t flags=REG(DMA2)&0x3du;
    REG(DMA2+8)=flags;
    if(flags&0x0d) { acquisition_stop(); fault(FAULT_DMA,1); return; }
    if((flags&0x30)==0x30) { acquisition_stop(); fault(FAULT_DMA_LATE,1); return; }
    if(flags&0x30) {
        unsigned offset=(flags&0x10) ? 0 : 2;
        sample_t sample={adc_data[offset],adc_data[offset+1],ticks};
        if(!sample_queue_push(&samples,sample)) fault(FAULT_QUEUE,1);
    }
}
void ADC_IRQHandler(void) {
    if(REG(ADC1)&(1u<<5)) {
        acquisition_stop(); REG(ADC1)=~(1u<<5); fault(FAULT_ADC,1);
    }
}
void USART2_IRQHandler(void) {
    uint32_t sr=REG(UART2);
    if(sr&0x2fu) { /* reading SR then DR clears RXNE and PE/FE/NE/ORE */
        uint8_t byte=(uint8_t)REG(UART2+4);
        if(sr&0xfu) fault(FAULT_UART,1);
        else if(!byte_queue_write(&rx,&byte,1)) fault(FAULT_RX,1);
    }
    if((sr&(1u<<7)) && (REG(UART2+12)&(1u<<7))) {
        uint8_t byte;
        if(byte_queue_pop(&tx,&byte)) REG(UART2+4)=byte;
        else REG(UART2+12)&=~(1u<<7);
    }
}
static void send(message_t message) {
    uint8_t frame[FRAME_BYTES]; encode_message(&message,frame);
    if(byte_queue_write(&tx,frame,sizeof frame)) REG(UART2+12)|=1u<<7;
    else app_fault(&app,FAULT_TX,1);
}
static void board_init(void) {
    __asm__ volatile("cpsid i");
    REG(RCC)|=1u;
    while(!(REG(RCC)&2u)) {}
    REG(RCC+8)=0; /* HSI; AHB, APB1 and APB2 all /1 */
    while(REG(RCC+8)&0xcu) {}
    REG(RCC)&=~(1u<<24);
    REG(0x40023c00u)=0; /* zero flash wait states at 16 MHz, 3.3 V */
    REG(RCC+0x30)|=(1u<<0)|(1u<<22); /* GPIOA, DMA2 */
    REG(RCC+0x40)|=(1u<<0)|(1u<<17); /* TIM2, USART2 */
    REG(RCC+0x44)|=1u<<8; /* ADC1 */
    (void)REG(RCC+0x30); (void)REG(RCC+0x40); (void)REG(RCC+0x44);
    REG(GPIOA)=(REG(GPIOA)&~0xcffu)|0x4afu; /* PA0/1 analog, PA2/3 AF, PA5 output */
    REG(GPIOA+0x0c)&=~0xffu;
    REG(GPIOA+0x20)=(REG(GPIOA+0x20)&~0xff00u)|0x7700u;
    REG(UART2+8)=139; /* 16 MHz / 139 = 115107.9 baud (-0.08%) */
    REG(UART2+16)=0; REG(UART2+20)=1; /* one stop bit; error interrupts */
    REG(UART2+12)=(1u<<13)|(1u<<5)|(1u<<3)|(1u<<2);
    nvic(38,2);
    REG(TIM2)=0; REG(TIM2+4)=0;
    REG(TIM2+0x28)=1599; REG(TIM2+0x2c)=99; /* 100 Hz at 16 MHz */
    REG(TIM2+0x14)=1; REG(TIM2+0x10)=0;
    REG(TIM2+4)=2u<<4; /* TRGO on update; UG was issued before ADC enable */
    REG(STREAM)=0; while(REG(STREAM)&1u) {}
    REG(DMA2+8)=0x3d;
    REG(STREAM+4)=4;
    REG(STREAM+8)=ADC1+0x4c;
    REG(STREAM+12)=(uint32_t)(uintptr_t)adc_data;
    REG(STREAM+20)=0; /* direct mode */
    REG(STREAM)=(1u<<16)|(1u<<13)|(1u<<11)|(1u<<10)|(1u<<8)|0x1eu;
    nvic(56,1);
    REG(0x40012304u)=0; /* common ADC prescaler APB2/2 = 8 MHz */
    REG(ADC1+4)=(1u<<8)|(1u<<26); /* scan, overrun interrupt */
    REG(ADC1+0x10)=6u|(6u<<3); /* 144 acquisition cycles, channels 0 and 1 */
    REG(ADC1+0x2c)=1u<<20; REG(ADC1+0x30)=0; REG(ADC1+0x34)=1u<<5;
    REG(ADC1)=0; REG(ADC1+8)=1;
    for(volatile unsigned delay=0;delay<1000;++delay) {} /* >3 us stabilization */
    REG(ADC1+8)|=(1u<<8)|(1u<<9)|(6u<<24)|(1u<<28);
    nvic(18,1);
    REG(STREAM)|=1; /* DMA ready before timer-triggered conversions */
    REG(0xe000ed08u)=0x08000000u;
    REG(0xe000ed20u)=(REG(0xe000ed20u)&0x00ffffffu)|(3u<<28);
    REG(0xe000e014u)=15999; REG(0xe000e018u)=0; REG(0xe000e010u)=7;
    REG(TIM2)|=1;
    __asm__ volatile("cpsie i");
}
int main(void) {
    app_init(&app,0); board_init(); parser_t parser={0};
    for(;;) {
        unsigned flags=atomic_exchange_explicit(&pending_faults,0,memory_order_relaxed);
        unsigned dropped=atomic_exchange_explicit(&pending_drops,0,memory_order_relaxed);
        app_fault(&app,(uint16_t)flags,dropped);
        sample_t sample;
        while(sample_queue_pop(&samples,&sample)) app_sample(&app,sample);
        uint8_t byte; message_t message;
        while(byte_queue_pop(&rx,&byte))
            if(parser_feed(&parser,byte,ticks,&message)) send(app_command(&app,message,ticks));
        if(app_poll(&app,ticks,&message)) send(message);
        unsigned period=app.faults ? 100 : 500;
        REG(GPIOA+0x18)=(ticks/period)&1 ? 1u<<5 : 1u<<21;
        __asm__ volatile("wfi");
    }
}
