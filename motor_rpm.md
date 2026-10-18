# Motor RPM feedback for the BlueROV2 Heavy

Findings on getting thruster RPM into ArduSub from AM32 ESCs, for a BlueROV2 Heavy (8 thrusters) on a Cube Orange+ or a CUAV X7+ Pro. Everything below was checked against source code; nothing here has been tested on a vehicle yet.

Sources:

| Name | Version |
| :--- | :--- |
| ArduSub | `aurapilot` fork, branch `realistic`, commit `7086516a` (ArduSub V4.7.0). Paths below are relative to that repository. |
| AM32 | v2.21 (`am32-firmware/AM32`, tag `v2.21`) |
| ESC | Aocoda-RC 70A/80A 3-8S single ESC, target `AORC_K_A_F421`, AM32 2.21 |

## Summary

| Question | Answer |
| :--- | :--- |
| RPM with PWM output | Not possible. ArduPilot reads ESC telemetry only when the motor outputs are digital (`libraries/AP_BLHeli/AP_BLHeli.cpp:1633`). |
| RPM on the signal wire (bidirectional DShot) | Only on FMU outputs marked `BIDIR` in the board's hwdef, in the `-bdshot` build |
| RPM on any other DShot output | Through the ESC's serial telemetry pad, wired to a flight controller UART |
| Cube Orange+ | Bidirectional DShot on AUX 1-6 only. MAIN 1-8 can run DShot but cannot return RPM on the signal wire. |
| CUAV X7+ Pro | Bidirectional DShot on outputs 1-4 only |
| RPM for the 4 horizontal thrusters of a BlueROV2 Heavy | Possible on both boards over the signal wire, no telemetry wire needed |

## ESC settings that matter

AM32 setting values as read from the ESC after the 2.21 update (EEPROM layout 4):

| Setting | Value | Meaning in AM32 2.21 |
| :--- | :--- | :--- |
| `BIDIRECTIONAL_MODE` | 1 | Reversible. Servo input: below neutral is reverse, above is forward (`Src/main.c:996-1008`). |
| Servo low / high / neutral | 175 / 75 / 126 | 1100 / 1900 / 1500 us (`low*2+750`, `high*2+1750`, `neutral+1374`, `Src/main.c:675-677`) |
| `SERVO_DEAD_BAND` | 50 | Stop band 1460-1540 us |
| `DISABLE_STICK_CALIBRATION` | 0 | Stick calibration enabled; it triggers when the ESC sees a large input before arming |
| `MOTOR_POLES` | 28 | Used for RPM conversion; ArduPilot needs the same value |
| `MOTOR_KV` | 7 | 300 KV (`value*40+20`) |
| `ESC_PROTOCOL` | 53 | Left over from the old layout. Any value of 10 or more means automatic input detection (`Src/main.c:743-777`). |
| `INTERVAL_TELEMETRY` | 0 | Interval serial telemetry off |

The ESC arms only after it has seen a stop command (neutral) for a while. ArduSub sends 1500 us to every motor while disarmed and when shut down (`libraries/AP_Motors/AP_Motors6DOF.cpp:225`, `:243-256`), which matches the ESC neutral.

## ArduPilot behaviour checked in source

| Behaviour | Detail | Source |
| :--- | :--- | :--- |
| Output range with DShot | If every motor output is digital, `MOT_PWM_MIN`/`MAX` are forced to 1000/2000. If only some are, they stay at 1100/1900. | `libraries/AP_Motors/AP_MotorsMulticopter.cpp:546-551`, `libraries/SRV_Channel/SRV_Channel.h:587` |
| 3D (reversible) DShot mapping | PWM is constrained to 1000-2000; below 1500 maps to DShot 1049-2047, above 1500 to 48-1047; 1500 is stop; disarmed sends 0 | `libraries/AP_HAL_ChibiOS/RCOutput.cpp:1708-1724` |
| Mixed PWM and DShot motors | DShot motors then receive 1100-1900, which maps to at most about 80% of the DShot range | Same two sources |
| Motor assignment pre-arm check | Every motor in the frame needs a `SERVOx_FUNCTION` | `libraries/AP_Motors/AP_MotorsMulticopter.cpp:976` |
| Serial telemetry requests | Round robin, one ESC per request, `SERVO_BLH_TRATE` is the rate per ESC, at least 2 ms between requests | `libraries/AP_BLHeli/AP_BLHeli.cpp:1637-1641`, `:1678-1691` |
| RPM sign | Bidirectional DShot telemetry carries magnitude only; no code adds a sign. Direction has to come from the commanded output. | `libraries/AP_HAL_ChibiOS/RCOutput_bdshot.cpp:572-573` |

BlueROV2 Heavy frame (`FRAME_CONFIG` 2, `VECTORED_6DOF`): motors 1-4 are horizontal (yaw, forward, lateral), motors 5-8 are vertical (throttle, roll, pitch) (`libraries/AP_Motors/AP_Motors6DOF.cpp:156-165`).

## Cube Orange+

| Outputs | Driven by | DShot | Bidirectional DShot | Timer groups |
| :--- | :--- | :--- | :--- | :--- |
| MAIN 1-8 | IOMCU, STM32F100 | Yes, with `BRD_IO_DSHOT` 1 | No | 1-2 TIM2, 3-4 TIM4, 5-8 TIM3 |
| AUX 1-6 | FMU, STM32H7 | Yes | Yes, `CubeOrangePlus-bdshot` build | 1-4 TIM1, 5-6 TIM4 |

- The IOMCU DShot firmware (`iomcu-dshot`, STM32F100) has no bidirectional support. IOMCU bidirectional DShot exists only on boards with an STM32F103 IOMCU (for example Pixhawk6X), and there only on a few channels (`libraries/AP_HAL_ChibiOS/hwdef/iomcu-f103-dshot/hwdef.inc:19-25`). This is a hardware limit, not a build option.
- 3D mapping works on MAIN DShot: the reversible mask is forwarded to the IOMCU (`libraries/AP_IOMCU/AP_IOMCU.cpp:1011`, `libraries/AP_IOMCU/iofirmware/iofirmware.cpp:1381`).
- Serial telemetry requests work on MAIN DShot (`libraries/AP_IOMCU/iofirmware/iofirmware.cpp:1146`).
- `CubeOrangePlus-bdshot` marks AUX 1, 3, 5 and 6 as `BIDIR`; AUX 2 and 4 share DMA with them (`libraries/AP_HAL_ChibiOS/hwdef/CubeOrangePlus-bdshot/hwdef.dat`).
- Outputs in the same timer group must use the same protocol, so a PWM device cannot share a group with DShot motors.
- Serial ports: SERIAL1 TELEM1, SERIAL2 TELEM2, SERIAL3 GPS1, SERIAL4 GPS2, SERIAL5 UART7, SERIAL6 second USB (`libraries/AP_HAL_ChibiOS/hwdef/CubeOrange/hwdef.inc:32`).

### Layout: RPM on the 4 horizontal thrusters

| Output | Connected to |
| :--- | :--- |
| AUX 1-4 | Horizontal motors 1-4, bidirectional DShot (RPM) |
| MAIN 1-4 | Vertical motors 5-8, DShot through the IOMCU (no RPM) |
| AUX 5 / AUX 6 | Lights / camera tilt (PWM) |
| MAIN 5-8 | Free |

```
FRAME_CONFIG 2
SERVO9_FUNCTION 33
SERVO10_FUNCTION 34
SERVO11_FUNCTION 35
SERVO12_FUNCTION 36
SERVO1_FUNCTION 37
SERVO2_FUNCTION 38
SERVO3_FUNCTION 39
SERVO4_FUNCTION 40
SERVO5_FUNCTION 0
SERVO6_FUNCTION 0
SERVO13_FUNCTION 181
SERVO14_FUNCTION 7
BRD_IO_DSHOT 1
MOT_PWM_TYPE 5
SERVO_BLH_BDMASK 3840
SERVO_BLH_3DMASK 3855
SERVO_BLH_POLES 28
SERVO_DSHOT_ESC 1
```

Lights and tilt move off AUX 1-2 because AUX 1-4 share TIM1 with the horizontal motors. Reboot after writing; `BRD_IO_DSHOT` loads the IOMCU DShot firmware only at boot.

### Other Cube layouts

| Layout | Result |
| :--- | :--- |
| All thrusters on MAIN, DShot, ESC telemetry pads wired to a UART | RPM for every thruster through the telemetry wire. Needs `BRD_IO_DSHOT` 1, `SERIALn_PROTOCOL` 16, `SERIALn_BAUD` 115. Rate per ESC is at most about 60 Hz with 8 ESCs. |
| 6 thrusters on AUX 1-6 (bidirectional DShot), 2 on MAIN with telemetry wires | RPM for all 8. Running bidirectional DShot and serial telemetry together was not checked. |
| All thrusters on PWM | Works, no RPM |

## CUAV X7+ Pro

The repository has one target for this family, `CUAV-X7` (board ID 1010, `AP_HW_CUAV_X7_PRO`, `Tools/AP_Bootloader/board_types.txt:131`). There is no separate X7+ target; confirm the board ID the X7+ Pro bootloader reports before flashing.

| Outputs | DShot | Bidirectional DShot | Timer group |
| :--- | :--- | :--- | :--- |
| 1-4 | Yes | Yes, `CUAV-X7-bdshot` build (`BIDIR` on 1 and 3, 2 and 4 share DMA) | TIM5 |
| 5-8 | Yes | No | TIM4 |
| 9-12 | Yes | No | TIM1 |
| 13-14 | No (`NODMA`), PWM only | No | TIM12 |

Sources: `libraries/AP_HAL_ChibiOS/hwdef/CUAV-X7/hwdef.dat:156-170`, `libraries/AP_HAL_ChibiOS/hwdef/CUAV-X7-bdshot/hwdef.dat:5-8`. The X7 has no IOMCU, so `BRD_IO_DSHOT` does not apply.

### Layout: RPM on the 4 horizontal thrusters

| Output | Connected to |
| :--- | :--- |
| 1-4 | Horizontal motors 1-4, bidirectional DShot (RPM) |
| 5-8 | Vertical motors 5-8, DShot (no RPM) |
| 13 / 14 | Lights / camera tilt (PWM) |
| 9-12 | Free |

```
FRAME_CONFIG 2
SERVO1_FUNCTION 33
SERVO2_FUNCTION 34
SERVO3_FUNCTION 35
SERVO4_FUNCTION 36
SERVO5_FUNCTION 37
SERVO6_FUNCTION 38
SERVO7_FUNCTION 39
SERVO8_FUNCTION 40
SERVO13_FUNCTION 181
SERVO14_FUNCTION 7
MOT_PWM_TYPE 5
SERVO_BLH_BDMASK 15
SERVO_BLH_3DMASK 255
SERVO_BLH_POLES 28
SERVO_DSHOT_ESC 1
```

Adding `BIDIR` to the TIM4 or TIM1 channels in a custom hwdef might extend bidirectional DShot beyond output 4, since every X7 output comes from the H743. Whether enough DMA streams are free has not been checked.

## Parameters used above

| Parameter | Value | Purpose |
| :--- | :--- | :--- |
| `MOT_PWM_TYPE` | 5 | DShot300; more tolerant of long leads than DShot600 |
| `SERVO_BLH_BDMASK` | Output bitmask | Outputs that return eRPM over bidirectional DShot. The parameter exists only in `-bdshot` builds. |
| `SERVO_BLH_3DMASK` | Output bitmask | Reversible outputs, 1500 us is stop. Must cover every thruster. |
| `SERVO_BLH_POLES` | 28 | Converts eRPM to mechanical RPM (default 14) |
| `SERVO_DSHOT_ESC` | 1 | BLHeli32/Kiss/AM32. 3 adds extended DShot telemetry (temperature, voltage, current). |
| `SERVO_BLH_TRATE` | Hz | Serial telemetry request rate per ESC |
| `BRD_IO_DSHOT` | 1 | DShot on the Cube MAIN outputs |
| `SERIALn_PROTOCOL` / `SERIALn_BAUD` | 16 / 115 | ESC serial telemetry at 115200 |

RPM shows up in MAVLink `ESC_TELEMETRY_1_TO_4`, in the dataflash `ESC` messages, and in Lua through `esc_telem:get_rpm()`.

## Requirements and open items

| Item | Status |
| :--- | :--- |
| All eight thruster ESCs must accept DShot (AM32) | Required by both layouts; mixing in PWM-only ESCs caps the DShot thrusters at about 80% |
| ESC telemetry pad | Needed only for the serial telemetry layouts. AM32 sends it on PB6 for this target; whether the board exposes a pad was not checked. |
| ESC calibration | The saved `esc1_config.bin` was identical to the EEPROM read right after flashing, so it holds no calibration. Read the ESC again in the configurator and save a new file. |
| IOMCU DShot firmware binary | Reversible support was confirmed in source, not in the prebuilt `Tools/IO_Firmware/iofirmware_cube_dshot_highpolh.bin` |
| Bidirectional DShot on AUX 2/4 (Cube) and outputs 2/4 (X7) | Depends on DMA sharing; confirm on the bench that all four horizontal thrusters report RPM |
| First test | One ESC, out of the water only briefly, nothing attached to the thruster |

## Cube Orange+ state on 2026-10-17

Read over MAVLink, before any change: ArduSub V4.7.0 (`7086516a`), `CubeOrangePlus-bdshot`, `FRAME_CONFIG` 1 (6 thrusters on MAIN 1-6), `MOT_PWM_TYPE` 0, `MOT_PWM_MIN`/`MAX` 1100/1900, AUX 1 lights (181), AUX 2 camera tilt (7), `SERVO_BLH_POLES` 14, `SERVO_DSHOT_ESC` 0, `BRD_IO_DSHOT` 0. With these settings the ESC already works over PWM on a MAIN output, without RPM.

## ArduSub needs `SERVO_BLH_MASK` and `SERVO_BLH_OTYPE`

`AP_BLHeli::init` takes the motor mask from `AP_Motors` only in Copter, Plane and Rover builds; `SERVO_BLH_AUTO` does not exist in Sub (`libraries/AP_BLHeli/AP_BLHeli.cpp:73`, `:1464-1481`). `SRV_Channels::init` is called with an empty mask (`libraries/AP_Vehicle/AP_Vehicle.cpp:452`), so in ArduSub the digital output mask is built only from `SERVO_BLH_MASK` with the type in `SERVO_BLH_OTYPE`. With `MOT_PWM_TYPE` alone the outputs do send DShot, but:

| Missing | Effect |
| :--- | :--- |
| Digital mask is 0 | No serial telemetry requests (`num_motors` 0), `MOT_PWM_MIN`/`MAX` stay 1100/1900 |
| `SERVO_BLH_3DMASK & digital_mask` is 0 | 3D (reversible) DShot mapping is not applied (`AP_BLHeli.cpp:1489`) |
| `SERVO_BLH_BDMASK & digital_mask` is 0 | Bidirectional DShot is not enabled (`AP_BLHeli.cpp:1495`) |

The parameter blocks in the Cube and X7 layouts above therefore also need these two lines. On the X7 with motors on outputs 1-8:

```
SERVO_BLH_MASK 255
SERVO_BLH_OTYPE 5
```

A non-zero `SERVO_BLH_MASK` also installs the BLHeli pass-through handler on the MAVLink port in `SERVO_BLH_PORT`; it does nothing until a configurator talks to it.

## X7: serial telemetry from several ESCs on one UART

| Fact | Source |
| :--- | :--- |
| ArduPilot uses one UART for ESC telemetry, the first port with protocol 16. A second port with 16 is ignored. | `AP_BLHeli.cpp:1515` |
| It asks one ESC at a time, by setting the telemetry bit in that ESC's next DShot frame, and assigns the 10-byte reply to that ESC | `AP_BLHeli.cpp:1678-1691`, `:1545`, `libraries/AP_HAL_ChibiOS/RCOutput.cpp:1734-1745` |
| Requests go round robin to every digital motor, including the ones that also have bidirectional DShot | `AP_BLHeli.cpp:1680-1686` |
| Request interval is `1/(SERVO_BLH_TRATE x motors)`, at least 2 ms. With 8 motors each ESC gets at most 62.5 Hz. The default `TRATE` of 10 gives 10 Hz per ESC. | `AP_BLHeli.cpp:1637-1641` |
| More than 10 bytes waiting means two ESCs answered; everything is discarded | `AP_BLHeli.cpp:1650-1654` |
| Requests are also sent while disarmed (throttle value 0 with the telemetry bit) | `RCOutput.cpp:1728-1740` |
| AM32 answers only when the telemetry bit is set; it never sends on its own while `INTERVAL_TELEMETRY` is 0 | AM32 v2.21 `Src/dshot.c:106-108` |
| AM32 runs the telemetry USART in single-wire half-duplex mode with the internal pull-up on, so the pin is released between replies | AM32 v2.21 `Mcu/f421/Src/serial_telemetry.c:28-32`, `:59` |
| `AORC_K_A_F421` is built with `USE_SERIAL_TELEMETRY` | AM32 v2.21 `Inc/targets.h` |
| Packet: temperature, voltage, current, consumption, eRPM/100, CRC8. RPM = value x 200 / poles, about 7.1 rpm per step with 28 poles. | `AP_BLHeli.cpp:1544-1555` |

The ESC telemetry pads can therefore share one RX pin: only the requested ESC drives the line, and a 10-byte reply at 115200 baud (about 0.9 ms) fits inside the 2 ms gap. The FC TX pin of that UART is not used.

X7 serial ports (`libraries/AP_HAL_ChibiOS/hwdef/CUAV-X7/hwdef.dat:22`): SERIAL1 TELEM1, SERIAL2 TELEM2, SERIAL3 GPS1, SERIAL4 GPS2, SERIAL5 UART8, SERIAL6 UART7 (debug).

### Wiring

- Every ESC `T` pad to the RX pin of one free UART, each through a 470 ohm to 1 kohm series resistor, so that a pin driven at the wrong time cannot short against another ESC.
- ESC signal ground to FC ground. Keep the telemetry leads short and away from the motor phase wires.
- Not checked: whether the Aocoda single ESC brings PB6 out to a pad, and whether the AT32F421 really releases the pin in half-duplex mode as the STM32 does. Check with a logic analyser on two ESCs before wiring all of them.

### Two layouts compared

| | A: all 8 on serial telemetry | B: 1-4 bidirectional DShot, 5-8 serial telemetry |
| :--- | :--- | :--- |
| Firmware | Standard `CUAV-X7` build | `CUAV-X7-bdshot` build |
| Extra wiring | 8 telemetry leads to one RX pin | 4 telemetry leads (or 8, see below) |
| Signal wire | One-way DShot | Outputs 1-4 become two-way: the ESC answers on the signal wire after each frame. More sensitive to lead length and noise; `SERVO_DSHOT_RATE` and DShot300 help. |
| RPM rate, horizontal 1-4 | At most 62.5 Hz | One reply per DShot frame, at the output rate (loop rate 400 Hz or more) |
| RPM rate, vertical 5-8 | At most 62.5 Hz | At most 62.5 Hz. Requests still go to 1-4 as well, so the rate for 5-8 does not go up. |
| RPM resolution | 100 eRPM, about 7 rpm | 1-4: from the eRPM period, finer at low speed; 5-8: about 7 rpm |
| RPM latency | Up to 16 ms between samples plus about 1 ms transfer | 1-4: one frame; 5-8: as in A |
| Bus load | 500 packets/s x 10 bytes, about 43 % of 115200 baud | Same serial load. The signal wires of 1-4 add the reply after every frame. |
| Temperature, voltage, current, mAh | All 8 | Only ESCs whose `T` pad is wired. Wiring 1-4 too costs nothing in rate and gives them as well. |
| Data quality | — | `get_erpm_error_rate` reports bad bidirectional frames per motor |
| Single point of failure | One bus for all 8. An ESC that holds the line low (fault, or an unpowered MCU clamping through its protection diode) cuts telemetry from all 8. | RPM of 1-4 does not depend on the shared bus |
| Sign | None. Direction comes from the commanded output in both layouts. | Same |

If the `T` pads of 1-4 are wired in layout B, serial and bidirectional values both go to `update_rpm` for the same motor (`AP_BLHeli.cpp:1548`, `libraries/AP_HAL_ChibiOS/RCOutput_bdshot.cpp:860`). The values agree, but the reported `update_rate_hz` jumps between the two sources.

### Parameters for layout B on the X7

```
FRAME_CONFIG 2
SERVO1_FUNCTION 33
SERVO2_FUNCTION 34
SERVO3_FUNCTION 35
SERVO4_FUNCTION 36
SERVO5_FUNCTION 37
SERVO6_FUNCTION 38
SERVO7_FUNCTION 39
SERVO8_FUNCTION 40
SERVO13_FUNCTION 181
SERVO14_FUNCTION 7
MOT_PWM_TYPE 5
SERVO_BLH_MASK 255
SERVO_BLH_OTYPE 5
SERVO_BLH_BDMASK 15
SERVO_BLH_3DMASK 255
SERVO_BLH_POLES 28
SERVO_BLH_TRATE 60
SERVO_DSHOT_ESC 1
SERIAL4_PROTOCOL 16
SERIAL4_BAUD 115
```

`SERIAL4` (GPS2) is an example; use any free port. For layout A, use the standard build and drop `SERVO_BLH_BDMASK`. On the ESC side nothing changes: `INTERVAL_TELEMETRY` stays 0.

A separate microcontroller that collects the telemetry is not needed. ArduPilot does not take ESC telemetry over MAVLink, and the microcontroller could not set the request bit because the signal wires belong to the FC.

## Decision (2026-10-17): layout A on the CUAV X7+ Pro

All eight thrusters report through AM32 serial telemetry on one shared UART. Bidirectional DShot is not used, so the standard `CUAV-X7` build is enough. Expected: RPM, temperature, voltage, current and consumption for every thruster at up to 62.5 Hz each, RPM in steps of about 7 rpm, no sign.

| Output | Connected to |
| :--- | :--- |
| 1-8 | Motors 1-8, DShot300, 3D |
| 13 / 14 | Lights / camera tilt (PWM) |
| RX of one free UART | `T` pads of all eight ESCs, each through 470 ohm to 1 kohm |

```
FRAME_CONFIG 2
SERVO1_FUNCTION 33
SERVO2_FUNCTION 34
SERVO3_FUNCTION 35
SERVO4_FUNCTION 36
SERVO5_FUNCTION 37
SERVO6_FUNCTION 38
SERVO7_FUNCTION 39
SERVO8_FUNCTION 40
SERVO13_FUNCTION 181
SERVO14_FUNCTION 7
MOT_PWM_TYPE 5
SERVO_BLH_MASK 255
SERVO_BLH_OTYPE 5
SERVO_BLH_3DMASK 255
SERVO_BLH_POLES 28
SERVO_BLH_TRATE 63
SERVO_DSHOT_ESC 1
SERIAL4_PROTOCOL 16
SERIAL4_BAUD 115
```

`SERVO_BLH_TRATE` 63 or more hits the 2 ms floor (62.5 Hz per ESC). Confirmed by the user: the Aocoda ESC has a `T` pad, and GPS1 (SERIAL3) and GPS2 (SERIAL4) are free on the vehicle. Both are `NODMA` UARTs, which is fine for 115200 baud receive. Open points: the half-duplex release on the AT32F421 (test below) and how a dead ESC on the shared line shows up in the log. This is also a fault case for the thesis: all eight telemetry streams stopping together points to the bus, not to the thrusters.

Release test for one powered, idle ESC: 10 kohm from the `T` pad to ground, measure the pad voltage. About 3.3 V means the pin is driven high between replies (push-pull); well under 1 V means it is released and only the internal pull-up (roughly 40 kohm) holds it. If it is driven, use a Schottky diode per ESC instead of the resistor (cathode at the `T` pad, anode on the shared line) and a 10 kohm pull-up from the line to 3.3 V: an ESC can then only pull the line low, which is all a UART needs. The diode version works in both cases.

Result (2026-10-17): invalid. The user measured below 1 V with 1 kohm, but the ESC was not beeping, so it was most likely in the bootloader, where the telemetry pin is not set up and floats; a floating pin also reads near 0 V. AM32 sets up the telemetry USART only at firmware start (`Mcu/f421/Src/peripherals.c:38-40`). Repeat with the bridge disconnected and the signal wire left open or tied to ground, so the ESC boots its firmware and beeps. With 1 kohm instead of 10 kohm a driven pin reads about 3.2 V and a released one about 0.1 V, so 1 kohm is fine for the test.
