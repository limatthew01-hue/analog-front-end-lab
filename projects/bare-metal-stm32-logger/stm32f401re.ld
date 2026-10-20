ENTRY(Reset_Handler)
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 512K
         RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 96K }
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
 .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
 .text : { *(.text*) *(.rodata*) . = ALIGN(4); } > FLASH
 .ARM.exidx : { *(.ARM.exidx*) } > FLASH
 _sidata = LOADADDR(.data);
 .data : { . = ALIGN(4); _sdata = .; *(.data*) . = ALIGN(4); _edata = .; } > RAM AT > FLASH
 .bss (NOLOAD) : { . = ALIGN(4); _sbss = .; *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .; } > RAM
 .stack (NOLOAD) : { . = ALIGN(8); . += 4096; } > RAM
 ASSERT(. <= _estack, "SRAM overflow including reserved 4 KiB stack")
 /DISCARD/ : { *(.comment*) *(.note*) }
}
