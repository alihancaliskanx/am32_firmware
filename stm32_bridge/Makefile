CC = arm-none-eabi-gcc
OBJCOPY = arm-none-eabi-objcopy
CFLAGS = -mcpu=cortex-m4 -mthumb -O2 -Wall -Wextra -ffreestanding -ffunction-sections
LDFLAGS = -nostdlib -T link.ld -Wl,--gc-sections

bridge.bin: bridge.elf
	$(OBJCOPY) -O binary $< $@

bridge.elf: main.c startup.c link.ld
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ main.c startup.c

clean:
	rm -f bridge.elf bridge.bin

.PHONY: clean
