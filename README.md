# am32_firmware

Bench setup for configuring and flashing an AM32 ESC (AT32F421, e.g. M4 70A 8S) from Linux, using an Arduino Uno as a USB-to-1-wire bridge instead of a flight controller.

## Contents

| Path | Description |
| :--- | :--- |
| `Arduino_AM32_pin3Link/` | 1-wire bridge sketch for the Uno, signal on D3 |
| `firmware/AM32_AORC_G_A_F421_2.20.hex` | AM32 2.20, target `AORC_G_A_F421` |
| `firmware/AM32_AORC_K_A_F421_2.20.hex` | AM32 2.20, target `AORC_K_A_F421` |

## Hardware

- Arduino Uno or clone (ATmega328P; CH340 clones show up as `/dev/ttyUSB0`)
- AM32 ESC
- LiPo battery for the ESC. The ESC MCU is not powered over the signal wire, so nothing responds without it.

| ESC lead | Connect to |
| :--- | :--- |
| Signal (white / yellow) | Uno D3 |
| Signal ground (black / brown) | Uno GND |
| Battery + / - | LiPo |

## The bridge

`Arduino_AM32_pin3Link.ino` disables the hardware UART and mirrors the USB serial RX/TX lines onto a single 1-wire pin. It implements no protocol and does not care about baud rate; the configurator talks to the ESC bootloader directly.

The pin is chosen at compile time with `#define OW_PIND3` (D3). `OW_PINB3` (D11) and `OW_PINB2` (D51 on a Mega) are also available.

Build and upload with [arduino-cli](https://arduino.github.io/arduino-cli/):

```bash
arduino-cli compile --fqbn arduino:avr:uno --upload -p /dev/ttyUSB0 Arduino_AM32_pin3Link
```

## Configuring and flashing the ESC

1. Close anything else that has the serial port open (`fuser -v /dev/ttyUSB0`).
2. Connect the LiPo to the ESC.
3. Open https://am32.ca/configurator in a browser with WebSerial support (Chromium, Chrome).
4. Choose **Direct Connect**, not flight controller passthrough.
5. Select the serial port and connect.
6. Read the settings and note the target name the ESC reports.
7. Flash the hex file whose target matches. The two targets have different pin mappings; flashing the wrong one can damage the ESC.

## What does not work with this setup

| Approach | Result |
| :--- | :--- |
| ArduPilot passthrough on a CubeOrange+ with `esc-configurator.com` | `Could not enable 4 way interface - reconnect flight controller`; MSP reports `MOTOR COUNT: 0` |
| This bridge with the BLHeliSuite desktop tool (`Esc_Config_Tool_1_82_Linux`) | `Didn't connect M1` |
| BLHeli 4-way interface firmware on the Uno (`4wArduino_m328P_16_MULTIv20006.hex`), signal on D11 | No reply to the 4-way init command at 19200 to 115200 baud |

The 4-way firmware replaces the bridge on the Uno only. Re-upload the sketch and move the signal wire back to D3 to recover.

## Beeping on power-up

Continuous beeping after the battery is connected means the ESC did not see a bootloader handshake, started the normal firmware, and is waiting for a throttle signal. It is not a fault.

## License

`Arduino_AM32_pin3Link.ino` is based on `Arduino1Wire.c` from the BLHeliSuite interface solutions for AVR, (C) 2014 4712, GPL-3.0. The firmware files are builds of [AM32](https://github.com/am32-firmware/AM32), GPL-3.0.
