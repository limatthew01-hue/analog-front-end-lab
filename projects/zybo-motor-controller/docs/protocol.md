# UART protocol and fault behavior

115200 baud, 8 data bits, no parity, 1 stop bit. All multi-byte fields are little-endian. `125000000 / 115200` is truncated to 1085 FPGA clocks/bit (about 115207.4 baud, +0.0064%).

## PC → FPGA: six-byte command

| Byte | Meaning |
|---|---|
| 0 | `0xA5` |
| 1 | Sequence modulo 256; diagnostic only, not replay protection |
| 2–3 | Unsigned target RPM, 0–600 |
| 4 | Bit 0: enable. Bit 1: clear faults. Bits 2–7 must be zero |
| 5 | CRC-8 of bytes 0–4 |

Clear is valid only with enable=0 and target=0. Other out-of-range or malformed frames are discarded without refreshing the heartbeat. A partial command expires after 20 ms with no received byte. Sync bytes inside a payload are treated as ordinary data. After a corrupted frame the receiver returns to searching for the next header; the PC repeats a full command every 100 ms.

CRC parameters: polynomial `0x07`, initial value 0, no reflection, XOR-out 0; `CRC("123456789")=0xF4` (CRC-8/SMBUS). CRC detects transmission errors; it is not authentication.

## FPGA → PC: 12-byte telemetry

| Byte | Meaning |
|---|---|
| 0 | `0x5A` |
| 1 | Telemetry sequence modulo 256 |
| 2–3 | Signed speed in 0.1 RPM |
| 4–5 | Requested target RPM |
| 6–7 | PI duty in permille, 0–900 |
| 8 | Status: bit 0 active, bit 1 physical arm, bit 2 link alive, bit 3 requested enable |
| 9 | Latched faults; see below |
| 10 | Invalid quadrature transition count, saturating at 255 |
| 11 | CRC-8 of bytes 0–10 |

Packets are atomic snapshots sent at 20 Hz. Requested target and enable can remain nonzero after a fault; `active` determines whether PWM is allowed. Duty returns to zero on the next clock after disabling, and PWM is gated off without waiting for a new frame. Stop is coast, not braking.

## Faults

| Mask | Fault | Detection |
|---|---|---|
| `0x01` | Driver | Synchronized FLT input LOW, including while disarmed |
| `0x02` | Link timeout | Armed nonzero run request but no valid command in 500 ms |
| `0x04` | No encoder motion | Active PI duty ≥250 permille and no encoder transition for 1000 ms |
| `0x08` | Invalid encoder transition | Both synchronized quadrature bits change together while active |
| `0x10` | Reverse motion | Three consecutive reverse transitions while active |

Faults latch. Renewed heartbeats do not automatically restart the motor. To clear, turn SW0 OFF, remove the fault cause, then send clear with enable=0 and target=0. A LOW driver fault cannot be cleared. BTN0 resets state; a continuing driver fault relatches after reset.

The no-motion detector is a heuristic, not current sensing: it does not detect every mechanical overload and is inactive below 25% requested duty. Invalid transitions while inactive are counted but do not latch a motion fault. The speed estimate remains available while coasting.
