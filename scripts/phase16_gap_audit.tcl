# Phase 16: READ-ONLY board-signoff gap audit of Phase 15 post-route DCP.
# Does not apply any XDC, change design properties or write a checkpoint/bitstream.
if {$argc != 2} {error "Usage: phase16_gap_audit.tcl <post_route.dcp> <fresh_output_dir>"}
lassign $argv checkpoint out
set checkpoint [file normalize $checkpoint]
set out [file normalize $out]
if {![file isfile $checkpoint]} {error "Missing Phase 15 checkpoint: $checkpoint"}
if {[file exists $out]} {error "Refusing to overwrite an existing Phase 16 directory: $out"}
file mkdir $out
open_checkpoint $checkpoint
set design [current_design]
if {$design ni {checkpoint_post_route faultscope_uart_top}} {
    error "Unexpected checkpoint design: $design"
}
proc p16prop {obj name} {
    if {[catch {get_property $name $obj} val] || $val eq ""} {return "UNSET"}
    return [string map [list "\t" " " "\n" " "] $val]
}
set expected_ports {clk led_alarm_o led_busy_o rst_n uart_rx_i uart_tx_o}
set actual_ports [lsort [get_ports]]
if {$actual_ports ne $expected_ports} {error "Unexpected FPGA interface: $actual_ports"}
set clocks [get_clocks -quiet board_clk_100mhz]
if {[llength $clocks] != 1} {error "Expected exactly one board_clk_100mhz"}
set period [get_property PERIOD [lindex $clocks 0]]
if {![string is double -strict $period] || abs($period - 10.0) > 0.00001} {
    error "Unexpected board period: $period"
}
set f [open [file join $out context.tsv] w]
puts $f "key\tvalue"
puts $f "phase\t16"
puts $f "design_name\t$design"
puts $f "vivado_version\t[version -short]"
puts $f "clock_name\tboard_clk_100mhz"
puts $f "clock_period_ns\t$period"
puts $f "cfgbvs\t[p16prop [current_design] CFGBVS]"
puts $f "config_voltage\t[p16prop [current_design] CONFIG_VOLTAGE]"
puts $f "clock_buffers\t[llength [get_cells -quiet -hierarchical -filter {REF_NAME =~ BUFG*}]]"
puts $f "input_buffers\t[llength [get_cells -quiet -hierarchical -filter {REF_NAME =~ IBUF*}]]"
puts $f "scope\tpost-route read-only diagnostic, NOT board signoff"
close $f
set f [open [file join $out ports.tsv] w]
puts $f "port\tdirection\tpackage_pin\tiostandard"
foreach name $expected_ports {
    set port [get_ports $name]
    puts $f "$name\t[p16prop $port DIRECTION]\t[p16prop $port PACKAGE_PIN]\t[p16prop $port IOSTANDARD]"
}
close $f
# Emit raw Vivado reports; never treat an empty CDC report as proof of physical safety.
report_drc -file [file join $out drc.rpt]
report_methodology -file [file join $out methodology.rpt]
report_clock_interaction -file [file join $out clock_interaction.rpt]
report_clock_networks -file [file join $out clock_networks.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $out timing_summary.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_cdc -details -file [file join $out cdc.rpt]
puts "PHASE16: read-only diagnostic files written; external/analog/board signoff remains open."
exit
