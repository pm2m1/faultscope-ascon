# Optional Vivado non-project out-of-context implementation/timing pilot.
# This is NOT a board wrapper, pin-constrained design, or bitstream flow.
# Usage from repository root on supported Linux/Windows with Vivado installed:
# vivado -mode batch -source scripts/phase10e_vivado_ooc.tcl -tclargs protected 10.0
if {$argc != 2} {
    error "Usage: -tclargs <baseline|instrumented|protected> <clock-period-ns>"
}
set design [lindex $argv 0]
set period [lindex $argv 1]
if {$design ni {baseline instrumented protected}} {error "Invalid design"}
if {![string is double -strict $period] || $period <= 0.0 || $period < 2.0 || $period > 1000.0} {
    error "Invalid period in ns; expected 2..1000"
}
set period [expr {double($period)}]
set part xc7a100tcsg324-1
set root [file normalize [pwd]]
if {![file isfile [file join $root pyproject.toml]]} {
    error "Run Vivado from the FaultScope-Ascon repository root"
}
set base [file join $root build reproduction phase10e vivado $design]
file mkdir $base
set rtl [file join $root rtl]
if {$design eq "baseline"} {
    set top ascon_aead_encrypt_bounded
    set names {ascon_round.sv ascon_permutation.sv ascon_aead_encrypt_bounded.sv}
} elseif {$design eq "instrumented"} {
    set top ascon_aead_encrypt_faultable
    set names {ascon_round.sv ascon_permutation_faultable.sv ascon_aead_encrypt_faultable.sv}
} else {
    set top ascon_aead_encrypt_temporal
    set names {ascon_round.sv ascon_permutation_faultable.sv ascon_permutation_temporal.sv ascon_aead_encrypt_temporal.sv}
}
create_project -in_memory -part $part
foreach name $names {
    set path [file join $rtl $name]
    if {![file exists $path]} {error "Missing required RTL: $path"}
    read_verilog -sv $path
}
puts "PHASE10E: Vivado out-of-context implementation top=$top part=$part clock_period_ns=$period"
puts "PHASE10E: No board-level pin map, IO delays, or host interface are provided"
# synth_design -mode out_of_context avoids treating 803 wide core port bits
# as 803 physical package pins. Constrain the internal core clock only.
# Make the target available to synthesis as well as implementation.
set xdc [file join $base internal_clock.xdc]
set constraint_file [open $xdc w]
puts $constraint_file "create_clock -name core_clk -period $period \[get_ports clk\]"
puts $constraint_file "set_property HD.CLK_SRC BUFGCTRL_X0Y0 \[get_ports clk\]"
close $constraint_file
read_xdc $xdc
synth_design -top $top -part $part -mode out_of_context -flatten_hierarchy rebuilt
set clocks [get_ports clk]
if {[llength $clocks] != 1} {error "Expected one clk port"}
if {[llength [get_clocks core_clk]] != 1} {error "Expected one constrained core clock"}
write_checkpoint -force [file join $base post_synth.dcp]
report_utilization -file [file join $base post_synth_utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $base post_synth_timing.rpt]
opt_design
place_design
write_checkpoint -force [file join $base post_place.dcp]
report_utilization -file [file join $base post_place_utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $base post_place_timing.rpt]
route_design
write_checkpoint -force [file join $base post_route.dcp]
report_utilization -file [file join $base post_route_utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $base post_route_timing.rpt]
report_route_status -file [file join $base post_route_status.rpt]
report_drc -file [file join $base post_route_drc.rpt]
check_timing -verbose -file [file join $base check_timing.rpt]
# This is a *register-to-register* setup path under one internal clock.
set timing_paths [get_timing_paths -delay_type max -max_paths 1 -from [all_registers] -to [all_registers]]
if {[llength $timing_paths] == 0} {error "No constrained register-to-register timing path; do not report pass"}
set wns [get_property SLACK [lindex $timing_paths 0]]
set hold_paths [get_timing_paths -delay_type min -max_paths 1 -from [all_registers] -to [all_registers]]
if {[llength $hold_paths] == 0} {error "No constrained hold path; do not report pass"}
set whs [get_property SLACK [lindex $hold_paths 0]]
set check_file [open [file join $base check_timing.rpt] r]
set check_text [read $check_file]; close $check_file
set coverage_ok [expr {[get_property HD.CLK_SRC [get_ports clk]] eq "BUFGCTRL_X0Y0"}]
foreach category {no_clock constant_clock unconstrained_internal_endpoints multiple_clock loops latch_loops} {
    if {![regexp [format {checking %s \(([0-9]+)\)} $category] $check_text unused count] || $count != 0} {set coverage_ok 0}
}
set route_file [open [file join $base post_route_status.rpt] r]
set route_text [read $route_file]; close $route_file
set route_ok [expr {
    [regexp {# of routable nets[. ]*:[ ]*([0-9]+)} $route_text unused routable] &&
    [regexp {# of fully routed nets[. ]*:[ ]*([0-9]+)} $route_text unused routed] &&
    [regexp {# of nets with routing errors[. ]*:[ ]*([0-9]+)} $route_text unused route_errors] &&
    $routable > 0 && $routable == $routed && $route_errors == 0}]
set drc_file [open [file join $base post_route_drc.rpt] r]
set drc_text [read $drc_file]; close $drc_file
set drc_ok [expr {![regexp {Critical Warning|Error} $drc_text]}]
set status [expr {!$coverage_ok || !$route_ok || !$drc_ok ? "NOT_VERIFIED" : ($wns >= 0.0 && $whs >= 0.0 ? "MET" : "FAILED")}]
set file [open [file join $base internal_timing_summary.txt] w]
puts $file "part=$part"
puts $file "top=$top"
puts $file "target_clock_period_ns=$period"
puts $file "post_route_worst_reg_to_reg_setup_slack_ns=$wns"
puts $file "post_route_worst_reg_to_reg_hold_slack_ns=$whs"
puts $file "internal_clock_coverage_verified=$coverage_ok"
puts $file "internal_reg_to_reg_target=$status"
puts $file "limitations=out_of_context; external_io_unconstrained; no_bitstream_or_board_wrapper"
close $file
puts "PHASE10E: out-of-context routed reg-to-reg setup/hold target $status, slack $wns ns"
puts "PHASE10E: inspect [file join $base post_route_timing.rpt] and check_timing.rpt for unconstrained endpoints"
