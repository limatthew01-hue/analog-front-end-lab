# Run from project root:
# vivado -mode batch -source scripts/build_vivado.tcl -tclargs xc7z020clg400-1
# Zybo Z7-10 uses xc7z010clg400-1. This is a PL-only design; no PS preset needed.
set part xc7z020clg400-1
if {$argc > 0} {set part [lindex $argv 0]}
if {$part ni {xc7z020clg400-1 xc7z010clg400-1}} {error "Choose the part printed on your Zybo Z7"}
file mkdir build
create_project -in_memory -part $part
read_verilog [glob rtl/*.v]
read_xdc constraints/zybo-z7.xdc
synth_design -top motor_top -part $part
opt_design
place_design
phys_opt_design
route_design
report_utilization -file build/utilization.rpt
report_timing_summary -report_unconstrained -file build/timing.rpt
report_drc -file build/drc.rpt
report_cdc -file build/cdc.rpt
set critical [get_drc_violations -quiet -filter {SEVERITY == Error}]
if {[llength $critical] > 0} {error "DRC errors: review build/drc.rpt"}
set paths [get_timing_paths -delay_type max -max_paths 1]
if {[llength $paths] == 0} {error "No timed paths: inspect constraints"}
if {[get_property SLACK $paths] < 0} {error "125 MHz timing not met: inspect build/timing.rpt"}
write_checkpoint -force build/motor_top_routed.dcp
write_bitstream -force build/motor_top.bit
puts "Built build/motor_top.bit. Inspect CDC, DRC, and timing reports before use."
