# Phase 12 native Vivado OOC implementation. No board pins or bitstream.
# Usage: -tclargs <baseline|instrumented|protected|uart_protected> <period-ns> <output-dir>
if {$argc != 3} { error "Expected design, clock period, output directory" }
lassign $argv design period out
if {$design ni {baseline instrumented protected uart_protected}} { error "Invalid design" }
if {![string is double -strict $period] || $period < 2 || $period > 1000} { error "Invalid period" }
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file normalize $out]
file mkdir $out
set part xc7a100tcsg324-1
if {[llength [get_parts -quiet $part]] != 1} { error "Required part unavailable: $part" }
set names {ascon_round.sv}
switch $design {
 baseline { set top ascon_aead_encrypt_bounded; lappend names ascon_permutation.sv ascon_aead_encrypt_bounded.sv }
 instrumented { set top ascon_aead_encrypt_faultable; lappend names ascon_permutation_faultable.sv ascon_aead_encrypt_faultable.sv }
 protected { set top ascon_aead_encrypt_temporal; lappend names ascon_permutation_faultable.sv ascon_permutation_temporal.sv ascon_aead_encrypt_temporal.sv }
 uart_protected { set top faultscope_uart_top; lappend names ascon_permutation_faultable.sv ascon_permutation_temporal.sv ascon_aead_encrypt_temporal.sv fs_reset_sync.sv fs_uart_rx.sv fs_uart_tx.sv faultscope_uart_top.sv }
}
set_param general.maxThreads 4
create_project -in_memory -part $part
foreach name $names { read_verilog -sv [file join $root rtl $name] }
set xdc [file join $out internal_clock.xdc]
set f [open $xdc w]
puts $f "create_clock -name core_clk -period $period \[get_ports clk\]"
puts $f "set_property HD.CLK_SRC BUFGCTRL_X0Y0 \[get_ports clk\]"
close $f
# Read before synthesis so synthesis sees the requested timing target.
read_xdc $xdc
set f [open [file join $out run_metadata.tsv] w]
puts $f "design\t$design"
puts $f "top\t$top"
puts $f "part\t$part"
puts $f "period_ns\t$period"
puts $f "vivado_version\t[version -short]"
puts $f "sources\t[join $names ,]"
puts $f "clock_source\tBUFGCTRL_X0Y0"
puts $f "settings\tOOC;flatten_hierarchy=rebuilt;default opt/place/route;maxThreads=4"
close $f
proc stage_reports {out stage} {
 write_checkpoint -force [file join $out ${stage}.dcp]
 report_utilization -file [file join $out ${stage}_utilization.rpt]
 report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $out ${stage}_timing.rpt]
}
synth_design -top $top -part $part -mode out_of_context -flatten_hierarchy rebuilt
if {[llength [get_ports -quiet clk]] != 1 || [llength [get_clocks -quiet core_clk]] != 1} { error "Missing unique internal clock" }
if {[llength [get_sites -quiet BUFGCTRL_X0Y0]] != 1 || [get_property HD.CLK_SRC [get_ports clk]] ne "BUFGCTRL_X0Y0"} {error "Missing OOC clock source context"}
set ports [lsort [get_ports]]
set f [open [file join $out top_ports.txt] w]; puts $f [join $ports \n]; close $f
if {$design eq "uart_protected" && $ports ne [lsort {clk rst_n uart_rx_i uart_tx_o led_busy_o led_alarm_o}]} { error "Unexpected UART ports: $ports" }
stage_reports $out post_synth
opt_design
place_design
stage_reports $out post_place
route_design
stage_reports $out post_route
report_route_status -file [file join $out post_route_status.rpt]
report_drc -file [file join $out post_route_drc.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_clocks -file [file join $out clocks.rpt]
report_clock_interaction -file [file join $out clock_interaction.rpt]
report_cdc -details -file [file join $out cdc.rpt]
set regs [all_registers -clock core_clk]
set setup [get_timing_paths -delay_type max -max_paths 1 -from $regs -to $regs]
set hold [get_timing_paths -delay_type min -max_paths 1 -from $regs -to $regs]
report_timing -delay_type max -max_paths 10 -from $regs -to $regs -path_type full_clock_expanded -file [file join $out internal_setup_paths.rpt]
report_timing -delay_type min -max_paths 10 -from $regs -to $regs -path_type full_clock_expanded -file [file join $out internal_hold_paths.rpt]
set f [open [file join $out internal_metrics.tsv] w]
puts $f "setup_path_count\t[llength $setup]"
puts $f "hold_path_count\t[llength $hold]"
foreach {label paths} [list setup $setup hold $hold] {
 if {[llength $paths]} {
  set p [lindex $paths 0]
  puts $f "${label}_slack_ns\t[get_property SLACK $p]"
  puts $f "${label}_startpoint\t[get_property STARTPOINT_PIN $p]"
  puts $f "${label}_endpoint\t[get_property ENDPOINT_PIN $p]"
 }
}
puts $f "register_count\t[llength $regs]"
puts $f "clock_period_ns\t[get_property PERIOD [get_clocks core_clk]]"
puts $f "clock_source\t[get_property HD.CLK_SRC [get_ports clk]]"
close $f
# Completion means reports exist, not a timing/CDC/board verdict.
set f [open [file join $out IMPLEMENTATION_COMPLETE] w]; puts $f "Reports generated; validate timing, DRC, routing, and constraints independently."; close $f
puts "PHASE12: Completed implementation for $design; external IO/reset timing remains unconstrained."
exit
