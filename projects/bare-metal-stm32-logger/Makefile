ARM_PREFIX ?= arm-none-eabi-
CC_HOST ?= gcc
PYTHON ?= python3
CFLAGS = -std=c11 -Wall -Wextra -Werror -Iinclude
ARMFLAGS = $(CFLAGS) -mcpu=cortex-m4 -mthumb -mfloat-abi=soft -Os -g3 -ffreestanding -fno-builtin -fdata-sections -ffunction-sections
.PHONY: all test replay clean
all: build/logger.elf build/logger.bin build/logger.hex
build:
	mkdir -p build
build/logger.elf: src/logger.c src/stm32f401.c src/runtime.c src/startup.S include/logger.h stm32f401re.ld Makefile | build
	$(ARM_PREFIX)gcc $(ARMFLAGS) -nostdlib -Wl,-z,noexecstack,--fatal-warnings,--gc-sections,-Map=build/logger.map -Tstm32f401re.ld src/startup.S src/logger.c src/stm32f401.c src/runtime.c -lgcc -o $@
	$(ARM_PREFIX)size $@
build/logger.bin: build/logger.elf
	$(ARM_PREFIX)objcopy -O binary $< $@
build/logger.hex: build/logger.elf
	$(ARM_PREFIX)objcopy -O ihex $< $@
test: | build
	$(CC_HOST) $(CFLAGS) -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer src/logger.c tests/test_core.c -o build/test_core
	./build/test_core
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v
replay: | build
	$(CC_HOST) $(CFLAGS) -O2 src/logger.c tests/replay.c -o build/replay
	$(PYTHON) scripts/replay.py
clean:
	rm -rf build
