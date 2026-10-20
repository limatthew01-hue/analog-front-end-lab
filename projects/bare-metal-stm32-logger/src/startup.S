.syntax unified
.cpu cortex-m4
.thumb
.section .isr_vector,"a",%progbits
.align 9
.word _estack
.word Reset_Handler
.rept 13
.word Default_Handler
.endr
.word SysTick_Handler
.set irq,0
.rept 85
 .if irq==18
 .word ADC_IRQHandler
 .elseif irq==38
 .word USART2_IRQHandler
 .elseif irq==56
 .word DMA2_Stream0_IRQHandler
 .else
 .word Default_Handler
 .endif
 .set irq,irq+1
.endr
.section .text.Reset_Handler,"ax",%progbits
.global Reset_Handler
.type Reset_Handler,%function
.thumb_func
Reset_Handler:
 ldr r0,=_sidata
 ldr r1,=_sdata
 ldr r2,=_edata
1: cmp r1,r2
 bcs 2f
 ldr r3,[r0],#4
 str r3,[r1],#4
 b 1b
2: ldr r1,=_sbss
 ldr r2,=_ebss
 movs r3,#0
3: cmp r1,r2
 bcs 4f
 str r3,[r1],#4
 b 3b
4: bl main
 b Default_Handler
.global Default_Handler
.type Default_Handler,%function
.thumb_func
Default_Handler:
 cpsid i
5: wfi
 b 5b
.section .note.GNU-stack,"",%progbits
