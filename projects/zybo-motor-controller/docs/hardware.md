# Hardware build and first run

**Status: the source and simulations are complete. No motor, Zybo board, or oscilloscope was connected during development. Vivado synthesis, timing closure, and physical measurements remain to be done.**

## Parts

| Part | Reference choice / requirement |
|---|---|
| FPGA board | Zybo Z7-10 or Z7-20; match the Vivado part to your board |
| Motor and encoder | Pololu #5133, 30:1 MP 6 V micro metal gearmotor with integrated 12 CPR encoder, or an equivalent after updating the CPR constant |
| Driver | Pololu #2130 DRV8833 carrier; channel A only |
| Motor supply | Regulated 6 V supply with current limiting appropriate to the motor; power the Zybo separately through its normal input |
| Serial adapter | USB-to-UART with **3.3 V TX/RX logic**, not RS-232 and not 5 V TTL |
| Connections | Motor mount; JST SH six-pin encoder cable and breakout; jumper wires; a real common ground connection |
| Passives | Two 10 kΩ pull-downs for AIN1/AIN2, one 10 kΩ pull-up for FLT to 3.3 V; suitable local motor-supply decoupling |
| Useful equipment | Multimeter; oscilloscope or logic analyzer for PWM/encoder checks |

The reference motor lists about 720 RPM no-load and 0.67 A theoretical stall current at 6 V. The carrier lists 1.2 A continuous per channel under its stated conditions. These ratings guide selection; they are not measurements of this build. Do not deliberately stall the motor for a demonstration. The carrier's default AISEN connection does **not** enable adjustable current regulation. Use the supply's current limit for initial testing.

## Wiring

Power everything off before changing connections. Motor power goes to the driver, never to a Pmod pin. Encoder VCC is **3.3 V** so its pulled-up outputs stay within the FPGA logic range. The reference encoder accepts 3.3 V independently of the 6 V motor winding supply.

| Zybo connection | FPGA package pin | Connect to |
|---|---|---|
| JE1 | V12 | Driver AIN1 (PWM), plus 10 kΩ to GND |
| JE2 | W16 | Driver AIN2 (held LOW), plus 10 kΩ to GND |
| JE3 | J15 | Encoder A, reference motor yellow wire |
| JE4 | H15 | Encoder B, reference motor white wire |
| JE7 | V13 | Driver FLT, plus 10 kΩ to **3.3 V** |
| JE8 | U17 | Unused; leave unconnected |
| JE9 | T17 | USB-UART adapter TX (PC → FPGA) |
| JE10 | Y17 | USB-UART adapter RX (FPGA → PC) |
| JE5 or JE11 | GND | Encoder ground, driver ground, motor-supply negative, adapter ground |
| JE6 or JE12 | 3.3 V | Encoder VCC and fault pull-up only |

Driver VIN connects to motor-supply +6 V. Driver AOUT1/AOUT2 connect to the motor winding terminals (reference motor red/black). Leave driver B channel unused. On the **specified Pololu carrier**, SLP is already pulled high; leave SLP unconnected to the Zybo. Different DRV8833 breakouts can wire SLP differently—check their schematic before substituting one.

Do not join the USB-UART adapter's power/VCC pin to the Zybo. Only TX, RX, and GND are needed. All grounds share a reference, but route motor return current directly to the driver/supply instead of through a thin encoder ground lead. The two AIN pull-downs keep the drive request LOW while the FPGA is unconfigured. Both inputs LOW mean **coast**, not active braking.

See [wiring.svg](wiring.svg) for the signal paths. The pin table above is the connection authority; confirm JE orientation from the board labels rather than from a breadboard photograph.

## Why an extra serial adapter?

The Zybo's built-in USB-UART is wired to the Zynq processing system's MIO pins. This project uses programmable logic alone. A separate 3.3 V adapter on JE9/JE10 avoids requiring a processing-system design or an AXI software bridge. The Zybo's normal USB cable is still used for JTAG programming/power as appropriate.

## Encoder calibration

`CPR_MILLI` is the number of **quadrature transitions per output-shaft revolution, multiplied by 1000**. Set it in the board top `rtl/motor_top.v`, the standalone core default `rtl/motor_core.v`, and the demo reference `host/model.py`. Count both edges of both encoder channels.

For the reference motor, the documented gearbox ratio is:

```text
gear ratio = (31 × 33 × 35 × 34) / (16 × 14 × 13 × 14)
           = 29.8609203297
output counts/revolution = 12 × ratio = 358.331043956
CPR_MILLI = 358331
```

The manufacturer's 12 CPR already includes all four quadrature edges. Do **not** multiply it by four again. A nominal “30:1” gear ratio is not the exact ratio. If using a different motor, change the constants and rebuild; do not assume 358.331 counts/revolution.

Positive rotation is the state sequence `00 → 01 → 11 → 10 → 00` for `{A,B}`. At first power-up, use a low target and check the sign of telemetry. If it is negative, stop, switch SW0 OFF, then swap A/B or set `ENCODER_INVERT=1` in `rtl/motor_top.v` and rebuild. Three consecutive reverse transitions while active latch a reverse fault.

## Build and program

1. Install AMD Vivado with support for the appropriate Zynq-7000 part.
2. From this project directory, run one of:

   ```sh
   # Zybo Z7-20
   vivado -mode batch -source scripts/build_vivado.tcl -tclargs xc7z020clg400-1
   # Zybo Z7-10
   vivado -mode batch -source scripts/build_vivado.tcl -tclargs xc7z010clg400-1
   ```

3. Inspect `build/timing.rpt`, `build/cdc.rpt`, and `build/drc.rpt`. The script refuses a bitstream if a setup path has negative slack or an Error-level DRC is present. Review other report findings too; running the script is not a substitute for checking constraints against your board.
4. Keep motor power off and SW0 OFF. In Vivado Hardware Manager, open the JTAG target and program `build/motor_top.bit`.
5. Check AIN2 is LOW, and AIN1 stays LOW with SW0 OFF, even after a PC Start command.
6. Turn on the motor supply at the correct voltage/current limit. Keep the shaft free and the motor securely mounted. Clear any startup fault with SW0 OFF.
7. Start the panel, select 100 RPM, press Start / Apply, then turn SW0 ON. Stay ready to switch SW0 OFF. Observe encoder sign and speed before trying higher targets or any load.

```sh
python -m host.panel --port /dev/ttyUSB0
# macOS example: --port /dev/cu.usbserial-XXXX
# Windows example: --port COM4
```

## Controls and indicators

| Control / LED | Behavior |
|---|---|
| SW0 | Physical arm; OFF inhibits PWM and resets the PI integral |
| BTN0 | Resets target, enable, link state, and faults; motor output becomes coast |
| LED0 | Control active |
| LED1 | Any latched fault |
| LED2 | Fresh accepted command within 500 ms |
| LED3 | PC requested enable (can be ON while SW0 is OFF) |
| Start / Apply | Sends the selected target; no motion unless SW0 is ON and fault-free |
| STOP / closing panel | Sends disabled, zero-speed commands; the motor coasts |
| Clear fault | Accepted only with SW0 OFF and a disabled, zero-speed command |

This is a small-motor educational controller. Its software interlocks are not a certified emergency stop. Disconnecting motor power is the physical fallback. A 0% command does not stop shaft rotation instantly.

## Measurements to collect yourself

Save CSV logs at 100, 200, and 300 RPM. Record the supply voltage, current limit, exact motor model, actual encoder CPR, and controller gains. Measure rise time, overshoot, final error, and recovery from a reproducible modest load. Compare telemetry against an independent tachometer if available. Add a short video and a wiring photograph only after the physical build works. Keep simulation results labeled separately from measured results.

## Primary references

- [Digilent Zybo Z7 reference manual, sections 7 and 16](https://digilent.com/reference/_media/reference/programmable-logic/zybo-z7/zybo-z7_rm.pdf)
- [Digilent master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Zybo-Z7-Master.xdc)
- [Pololu DRV8833 carrier #2130](https://www.pololu.com/product/2130)
- [Pololu reference motor #5133 and exact gear ratio](https://www.pololu.com/product/5133)
