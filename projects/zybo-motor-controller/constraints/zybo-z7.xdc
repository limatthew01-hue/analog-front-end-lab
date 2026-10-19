# Zybo Z7 Rev. B pin mapping adapted from Digilent's MIT-licensed master XDC.
# https://github.com/Digilent/digilent-xdc/blob/master/Zybo-Z7-Master.xdc
# See DIGILENT_LICENSE.txt. Verify board revision before wiring.
set_property -dict {PACKAGE_PIN K17 IOSTANDARD LVCMOS33} [get_ports sysclk]
create_clock -name sysclk -period 8.000 [get_ports sysclk]
set_property -dict {PACKAGE_PIN K18 IOSTANDARD LVCMOS33} [get_ports btn_reset]
set_property -dict {PACKAGE_PIN G15 IOSTANDARD LVCMOS33} [get_ports arm_switch]
set_property -dict {PACKAGE_PIN M14 IOSTANDARD LVCMOS33} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN M15 IOSTANDARD LVCMOS33} [get_ports {led[1]}]
set_property -dict {PACKAGE_PIN G14 IOSTANDARD LVCMOS33} [get_ports {led[2]}]
set_property -dict {PACKAGE_PIN D18 IOSTANDARD LVCMOS33} [get_ports {led[3]}]

# JE physical pins 1,2,3,4,7,9,10. JE8 is intentionally unused.
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports motor_in1]
set_property -dict {PACKAGE_PIN W16 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports motor_in2]
set_property -dict {PACKAGE_PIN J15 IOSTANDARD LVCMOS33} [get_ports encoder_a]
set_property -dict {PACKAGE_PIN H15 IOSTANDARD LVCMOS33} [get_ports encoder_b]
set_property -dict {PACKAGE_PIN V13 IOSTANDARD LVCMOS33} [get_ports driver_fault_n]
set_property -dict {PACKAGE_PIN T17 IOSTANDARD LVCMOS33 PULLUP true} [get_ports uart_rx_pin]
set_property -dict {PACKAGE_PIN Y17 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports uart_tx_pin]

# Exclude ONLY the asynchronous source -> first synchronizer stage.
# Stage 1 -> stage 2 and all control logic remain timed at 125 MHz.
set_false_path -from [get_ports {btn_reset arm_switch driver_fault_n}] -to [get_pins -hier -filter {NAME =~ *io_meta_reg*/D}]
set_false_path -from [get_ports {encoder_a encoder_b}] -to [get_pins -hier -filter {NAME =~ *enc_meta_reg*/D}]
set_false_path -from [get_ports uart_rx_pin] -to [get_pins -hier -filter {NAME =~ *rx_meta_reg*/D}]
# External devices are asynchronous; their output delays are not clock-relative.
set_false_path -to [get_ports {motor_in1 motor_in2 uart_tx_pin led[*]}]
