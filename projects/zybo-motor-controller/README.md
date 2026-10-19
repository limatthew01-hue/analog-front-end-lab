# Zybo motor speed controller

A one-direction DC motor controller for the Zybo Z7, with encoder feedback, fixed-point PI control, and a Python operator panel. The design aims to keep a small motor near a requested speed when its load changes.

**Current status:** RTL and software tested in simulation. Vivado synthesis, timing closure, the desktop panel, and a physical motor connection still need local verification. There are no measured motor results in this repository.

![Switched-PWM simulation](results/closed_loop.svg)

## What is implemented

- 20 kHz PWM from the board's 125 MHz clock; duty capped at 90%.
- Four-edge quadrature decoding with input synchronizers and invalid-transition detection.
- 50 Hz speed estimation and PI control with conditional integration to limit windup.
- 0–600 RPM target commands over a CRC-protected UART link.
- Physical arm input, driver-fault input, heartbeat timeout, missing-motion detection, and reverse-motion detection.
- Latched faults that require a stopped, disarmed clear command.
- Python panel with separate simulation and hardware modes, Start/Apply, Stop, a speed plot, and CSV export.
- Seven RTL testbenches, 19 Python tests, an integer controller reference, and reproducible simulation reports.

The controller uses the FPGA's programmable logic only. It needs a **separate 3.3 V USB-to-UART adapter**; the Zybo's built-in USB serial port belongs to its processing system.

## Run without hardware

Use Python 3.11 or newer. Run these commands from this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m host.panel --demo
```

On Windows, activate with `.venv\Scripts\activate`. If Tkinter is missing on Linux, install your distribution's `python3-tk` package. The demo checkbox simulates the physical arm switch. Start at 100 RPM, turn that simulated switch on, then use “Apply simulated load” to see feedback compensate. The demo uses the averaged Python model; the checked RTL trace above comes from the Verilog testbench.

To reproduce verification and figures, install [Icarus Verilog](https://steveicarus.github.io/iverilog/), including `iverilog` and `vvp`, then run:

```sh
python scripts/run_checks.py
python scripts/report.py
```

For just the standard-library Python tests:

```sh
python -m unittest discover -s tests -v
```

## Hardware version

The reference parts are a Zybo Z7, a 6 V motor with quadrature encoder, a DRV8833 driver, a suitable separate motor supply, and a 3.3 V USB-UART adapter. The included encoder constant is for Pololu #5133, not an arbitrary motor.

Read the [parts, exact pin connections, encoder calibration, and first-run procedure](docs/hardware.md) **before connecting anything**. Motor winding power must not come from a Pmod pin. The output is PWM/coast in one direction; stopping does not actively brake the shaft.

```sh
# Match the part to the board: Z7-20 shown here.
vivado -mode batch -source scripts/build_vivado.tcl -tclargs xc7z020clg400-1
# Program build/motor_top.bit with Vivado Hardware Manager, then:
python -m host.panel --port /dev/ttyUSB0
```

SW0 is the arm input. BTN0 resets the controller. Fault clear requires SW0 OFF and a zero-speed, disabled command. Removing a fault or restoring a heartbeat does not restart a latched controller. [Protocol and fault definitions](docs/protocol.md).

## Controller

For each 20 ms encoder window:

```text
raw_speed_x10 = trunc(counts × 600000 × 50 / CPR_MILLI)
filtered_speed_x10 += trunc((raw_speed_x10 - filtered_speed_x10) / 4)
error_x10 = 10 × target_RPM - previous_filtered_speed_x10
candidate_I = I + 24 × error_x10
candidate_u = 256 × error_x10 + candidate_I
duty_permille = clamp(trunc(candidate_u / 2560), 0, 900)
```

The candidate integral is retained only if it is not driving the output farther into saturation. Disable and a zero target reset the integral. All signed divisions truncate toward zero. `Kp=1.0` permille/RPM and `Ki=4.6875` permille/(RPM·s) at 50 Hz. The PI sees the previous filtered estimate because both registers update on the same clock edge. PWM duty changes at frame boundaries; disabling gates the output without waiting for that boundary.

## Simulation results

The switched-PWM RTL simulation requests 300 RPM, applies an assumed load at 2 s, and stops at 4 s. It uses a first-order mechanical model and a scaled simulation clock; the model has not been identified from a physical motor. See [the full results report](results/report.md), [trace](results/rtl_closed_loop.csv), [parameters](results/metrics.json), and [verification log](results/verification.txt).

The separate 54-case averaged-model sweep changes motor gain, time constant, target, and load. It includes targets that cannot be reached within the duty cap. [Sensitivity results](results/sensitivity.csv).

## Files

| Directory | Contents |
|---|---|
| `rtl/` | PWM, quadrature decoder, PI, fault core, UART, protocol, board top |
| `host/` | Wire protocol, fixed-point reference, assumed plant, Tk panel |
| `sim/` | Self-checking RTL benches and behavioral motor model |
| `tests/` | Python protocol and control tests |
| `constraints/` | Zybo Z7 pin assignments and upstream pin-map license |
| `scripts/` | Test runner, reports, Vivado implementation script |
| `docs/` | Hardware and protocol guides, wiring figure |
| `results/` | Reproducible CSV, metrics, figures, test output |

Further work: verify the FPGA timing reports, build and measure the hardware, tune the gains, and compare the encoder-derived RPM with an independent tachometer. Current measurement and bidirectional control are possible extensions, rather than claims about this version.
