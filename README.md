# am32_firmware

Bench setup for flashing and configuring an AM32 ESC (AT32F421) from Linux without a flight controller, using a NUCLEO-F446RE or an Arduino Uno as a USB-to-1-wire bridge. `motor_rpm.md` covers getting thruster RPM from these ESCs into ArduSub.

## Contents

| Path | Description |
| :--- | :--- |
| `stm32_bridge/` | 1-wire bridge firmware for a NUCLEO-F446RE, signal on D2 (PA10) |
| `tools/flash_direct.py` | Flashes an AM32 hex through the bridge and verifies it |
| `Arduino_AM32_pin3Link/` | 1-wire bridge sketch for the Uno, signal on D3 |
| `motor_rpm.md` | Thruster RPM feedback in ArduSub on a Cube Orange+ or CUAV X7+ Pro: output limits, telemetry options, parameters |
| `firmware/AM32_AORC_K_A_F421_2.21.hex` | AM32 2.21, target `AORC_K_A_F421` |
| `firmware/AM32_AORC_K_A_F421_2.20.hex` | AM32 2.20, target `AORC_K_A_F421` |
| `firmware/AM32_AORC_G_A_F421_2.20.hex` | AM32 2.20, target `AORC_G_A_F421` |

## Hardware

- NUCLEO-F446RE; its ST-LINK/V2-1 shows up as `/dev/ttyACM0`. Alternatively an Arduino Uno or clone (CH340 clones show up as `/dev/ttyUSB0`).
- AM32 ESC. Tested with an Aocoda-RC 70A/80A 3-8S single ESC, target `AORC_K_A_F421`.
- LiPo battery for the ESC. The ESC MCU is not powered over the signal wire, so nothing responds without it.

| ESC lead | NUCLEO-F446RE | Arduino Uno |
| :--- | :--- | :--- |
| Signal (white / yellow) | D2 (PA10) | D3 |
| Signal ground (black / brown) | GND | GND |
| Battery + / - | LiPo | LiPo |

## STM32 bridge

`stm32_bridge` is bare-metal firmware. It uses the ST-LINK virtual COM port pins (PA2/PA3, connected by default on the Nucleo) as plain GPIO and mirrors them onto the ESC signal pin, so it does not depend on the baud rate.

While the host is silent the bridge drives the signal pin high (push-pull). At power-up the AM32 bootloader samples the pin with its own pull-down enabled and stays in the bootloader only if it never reads low; a weak pull-up such as the Uno's can lose that. Host activity releases the pin to an input with pull-up so the ESC can answer, and 500 ms of silence drives it high again. LD2 is lit while the pin is held high.

Build with the GNU Arm toolchain (`arm-none-eabi-gcc`):

```bash
make -C stm32_bridge
```

Flash the board by copying `stm32_bridge/bridge.bin` to the ST-LINK USB drive (`NOD_F446RE` or `NODE_F446RE`). The board restarts into the bridge when the copy finishes.

With the bridge running, connect the ESC battery: the ESC stays in the bootloader and does not beep.

## Flashing the ESC

`tools/flash_direct.py` needs Python 3 and pyserial. It talks to the AM32 bootloader through the bridge with the same command sequence as the AM32 configurator's direct-connect mode:

1. Checks that the bootloader reports the 32 KB F421 signature and that the target name stored on the ESC matches the one in the hex file.
2. Saves the 184-byte settings block to the `--backup` file.
3. Clears the settings boot byte, so an interrupted flash cannot start a half-written image.
4. Writes the image from 0x1000 in 64-byte chunks.
5. Reads the whole image back and compares it.
6. Writes the settings back with the boot byte set, then starts the firmware.

Close every other program that has the port open (`fuser -v /dev/ttyACM0`). Check the target without writing anything:

```bash
python3 tools/flash_direct.py /dev/ttyACM0 firmware/AM32_AORC_K_A_F421_2.21.hex --backup eeprom_backup.bin --dry-run
```

Flash:

```bash
python3 tools/flash_direct.py /dev/ttyACM0 firmware/AM32_AORC_K_A_F421_2.21.hex --backup eeprom_backup.bin
```

A flash takes about 40 seconds. If it fails, the boot byte stays cleared and the ESC remains in the bootloader; run the command again. The bootloader itself is never written.

After the update the ESC plays its startup tune once, finds no throttle signal, restarts, and stays in the bootloader because the bridge holds the line high. AM32 2.21 converts a layout 2 settings block to layout 4 on its first start; fields that layout 2 did not have get default values.

## Configuring the ESC

The AM32 configurator works through the STM32 bridge:

1. Close every other program that has the port open (`fuser -v /dev/ttyACM0`).
2. Open https://am32.ca/configurator in a new Chromium tab.
3. Select the ST-LINK port (`0x0483:0x374b`), tick **Direct**, keep 19200 baud and connect. The ST-LINK vendor ID is not on the configurator's list of direct-connect adapters, so the box has to be ticked by hand.
4. The configurator reads the ESC on connect. Click the ESC card to show its settings.

The first attempts, with AM32 2.17 still on the ESC, showed no ESC card, and Flash then looked for a file named `AM32_ERROR_<version>.hex`. After the update to 2.21, in a new tab, the ESC card appeared and the settings could be read and saved to a file. Writing settings back has not been confirmed. The cause of the earlier failure was not found. If it happens again, reload the page and reconnect; `tools/flash_direct.py` does not depend on the configurator.

Flashing from the configurator through the bridge has not been tried; the update to 2.21 was done with `tools/flash_direct.py`.

## Arduino bridge

`Arduino_AM32_pin3Link.ino` disables the hardware UART and mirrors the USB serial RX/TX lines onto a single 1-wire pin. The pin is chosen at compile time with `#define OW_PIND3` (D3). `OW_PINB3` (D11) and `OW_PINB2` (D51 on a Mega) are also available.

Build and upload with [arduino-cli](https://arduino.github.io/arduino-cli/):

```bash
arduino-cli compile --fqbn arduino:avr:uno --upload -p /dev/ttyUSB0 Arduino_AM32_pin3Link
```

The sketch echoes the host's low bits without reading the signal pin, so a clean echo does not prove that the pin works. On the Uno used here, D3 was stuck high, and the ESC never answered through it.

## What does not work with this setup

| Approach | Result |
| :--- | :--- |
| ArduPilot passthrough on a CubeOrange+ with `esc-configurator.com` | `Could not enable 4 way interface - reconnect flight controller`; MSP reports `MOTOR COUNT: 0` |
| Arduino bridge with the BLHeliSuite desktop tool (`Esc_Config_Tool_1_82_Linux`) | `Didn't connect M1` |
| BLHeli 4-way interface firmware on the Uno (`4wArduino_m328P_16_MULTIv20006.hex`), signal on D11 | No reply to the 4-way init command at 19200 to 115200 baud |

## Beeping on power-up

Continuous beeping after the battery is connected means the ESC is running its firmware without a throttle signal: it restarts every two seconds and plays the startup tune each time. It did not stay in the bootloader because the signal pin was not held high at power-up. It is not a fault.

## License

`Arduino_AM32_pin3Link.ino` is based on `Arduino1Wire.c` from the BLHeliSuite interface solutions for AVR, (C) 2014 4712, GPL-3.0. The firmware files are builds of [AM32](https://github.com/am32-firmware/AM32), GPL-3.0.
