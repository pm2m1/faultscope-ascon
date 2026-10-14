# Phase 17 configuration-property full-board candidate for PROVISIONAL Nexys 4 DDR Rev. C.
# No physical board, no bitstream, and no external I/O timing or MTBF signoff.
# Usage: vivado -mode batch -source scripts/phase17_cfg_impl.tcl -tclargs <phase15_xdc> <cfg_overlay_xdc> <output_directory>
if {$argc != 3} { error "Expected base XDC, config overlay XDC, output directory" }
lassign $argv xdc overlay out
set xdc [file normalize $xdc]
set overlay [file normalize $overlay]
set out [file normalize $out]
set root [file normalize [file join [file dirname [info script]] ..]]
if {![file isfile $xdc]} { error "Missing Phase 15 XDC: $xdc" }
if {![file isfile $overlay]} { error "Missing config overlay: $overlay" }
if {[file exists [file join $out IMPLEMENTATION_COMPLETE]]} {error "Refusing to overwrite completed implementation"}
file mkdir $out
set_param general.maxThreads 4
set part xc7a100tcsg324-1
create_project -in_memory -part $part
set names {ascon_round.sv ascon_permutation_faultable.sv ascon_permutation_temporal.sv ascon_aead_encrypt_temporal.sv fs_reset_sync.sv fs_uart_rx.sv fs_uart_tx.sv faultscope_uart_top.sv}
foreach name $names { read_verilog -sv [file join $root rtl $name] }
read_xdc $xdc


# Full device-level synthesis. Do NOT use -mode out_of_context or HD.CLK_SRC.
synth_design -top faultscope_uart_top -part $part -flatten_hierarchy rebuilt
# The XDC is read before synthesis so timing and IO constraints are applied.
# Vivado requires an open synthesized/elaborated design for get_clocks.
# Never query get_clocks against the empty in-memory project. Validate the
# actual synthesized clock object before implementation or writing provenance.
if {[llength [get_clocks -quiet board_clk_100mhz]] != 1} { error "Required board clock missing" }
set clock [get_clocks board_clk_100mhz]
if {[expr {abs([get_property PERIOD $clock] - 10.0)}] > 0.00001} {error "Incorrect 100 MHz clock period"}
# Explicitly apply the *separate* board config overlay against the OPEN synthesized design.
# This must precede opt/place/route and the new checkpoint; do not patch Phase 15 DCP.
read_xdc $overlay
if {[get_property CFGBVS [current_design]] ne "VCCO"} {
    error "Missing expected CFGBVS=VCCO on new synthesized design"
}
if {![string is double -strict [get_property CONFIG_VOLTAGE [current_design]]] ||
    abs(double([get_property CONFIG_VOLTAGE [current_design]]) - 3.3) > 0.00001} {
    error "Missing expected CONFIG_VOLTAGE=3.3"
}
set f [open [file join $out source_context.tsv] w]
puts $f "key\tvalue"
puts $f "phase\t17"
puts $f "board\tPROVISIONAL Nexys 4 DDR Rev. C"
puts $f "part\t$part"
puts $f "top\tfaultscope_uart_top"
puts $f "vivado_version\t[version -short]"
puts $f "rtl_sources\t[join $names ,]"
puts $f "xdc\t$xdc"
puts $f "overlay\t$overlay"
puts $f "cfgbvs\t[get_property CFGBVS [current_design]]"
puts $f "config_voltage\t[get_property CONFIG_VOLTAGE [current_design]]"
puts $f "design_mode\tfull_board_not_ooc"
puts $f "clock_period_ns\t[get_property PERIOD $clock]"
puts $f "scope\tFull routed FPGA design; external IO timing and physical verification remain unverified"
close $f
if {[llength [get_cells -quiet -hierarchical -filter {REF_NAME =~ IBUF*}]] == 0} {
    error "No physical input buffers after full-board synthesis"
}
set required_ports [lsort {clk rst_n uart_rx_i uart_tx_o led_busy_o led_alarm_o}]
set found_ports [lsort [get_ports]]
if {$required_ports ne $found_ports} { error "Unexpected top-level ports: $found_ports" }
write_checkpoint -force [file join $out post_synth.dcp]
report_utilization -file [file join $out post_synth_utilization.rpt]

opt_design
place_design
write_checkpoint -force [file join $out post_place.dcp]
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $out post_place_timing.rpt]

route_design
# Verify properties remained on routed design before creating its independent checkpoint.
if {[get_property CFGBVS [current_design]] ne "VCCO" ||
    abs(double([get_property CONFIG_VOLTAGE [current_design]]) - 3.3) > 0.00001} {
    error "Config properties did not persist through route_design"
}
write_checkpoint -force [file join $out post_route.dcp]
report_utilization -file [file join $out post_route_utilization.rpt]
report_route_status -file [file join $out post_route_status.rpt]
report_drc -file [file join $out post_route_drc.rpt]
report_methodology -file [file join $out methodology.rpt]
report_clock_interaction -file [file join $out clock_interaction.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $out post_route_timing.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_clocks -file [file join $out clocks.rpt]
report_clock_networks -file [file join $out clock_networks.rpt]
report_cdc -details -file [file join $out cdc.rpt]

set f [open [file join $out pin_assignment.tsv] w]
puts $f "port\tdirection\tpackage_pin\tiostandard"
foreach p [get_ports] {
    puts $f "[get_property NAME $p]\t[get_property DIRECTION $p]\t[get_property PACKAGE_PIN $p]\t[get_property IOSTANDARD $p]"
}
close $f

# Additional evidence on the reset-release and UART RX synchronizer flip-flops.
set f [open [file join $out synchronizer_cells.tsv] w]
puts $f "cell\tref_name\tasync_reg\tloc\tbel"
set expected {
    {u_reset_sync/release_pipe_q_reg[0]}
    {u_reset_sync/release_pipe_q_reg[1]}
    {u_reset_sync/release_pipe_q_reg[2]}
    {receiver/sync_q_reg[0]}
    {receiver/sync_q_reg[1]}
}
foreach name $expected {
    set ff [get_cells -quiet $name]
    if {[llength $ff] != 1} {error "Missing or duplicate mapped synchronizer register: $name"}
    set primitive [get_property REF_NAME $ff]
    if {![string match "FD*" $primitive]} {error "Unexpected synchronizer primitive: $name $primitive"}
    if {[string toupper [get_property ASYNC_REG $ff]] ni {1 TRUE}} {error "Lost ASYNC_REG attribute on $name"}
    set loc [get_property LOC $ff]
    set bel [get_property BEL $ff]
    if {$loc eq "" || $bel eq ""} {error "Unplaced synchronizer register $name"}
    puts $f "$name\t$primitive\t[get_property ASYNC_REG $ff]\t$loc\t$bel"
}
close $f

# Direct Q-to-D connection checks mirror the previously verified Phase 14 audit.
proc phase17_pin_nets {cell pin_name} {
    set pins [get_pins -quiet -of_objects $cell -filter "REF_PIN_NAME == $pin_name"]
    if {[llength $pins] != 1} { return {} }
    set nets [get_nets -quiet -segments -of_objects $pins]
    set names {}
    foreach net $nets { lappend names [get_property NAME $net] }
    return [lsort -unique $names]
}
set ef [open [file join $out synchronizer_edges.tsv] w]
puts $ef "group\tfrom_stage\tto_stage\tnet\tstatus"
foreach {group src dst} {reset 0 1 reset 1 2 rx 0 1} {
    if {$group eq "reset"} {
        set a "u_reset_sync/release_pipe_q_reg\[$src\]"
        set b "u_reset_sync/release_pipe_q_reg\[$dst\]"
    } else {
        set a "receiver/sync_q_reg\[$src\]"
        set b "receiver/sync_q_reg\[$dst\]"
    }
    set qa [phase17_pin_nets [get_cells $a] Q]
    set db [phase17_pin_nets [get_cells $b] D]
    set shared "-"
    foreach n $qa { if {[lsearch -exact $db $n] != -1} {set shared $n; break} }
    set state "DIRECT"
    if {$shared eq "-"} {set state "NOT_VERIFIED"}
    puts $ef "$group\t$src\t$dst\t$shared\t$state"
    if {$state ne "DIRECT"} {error "Missing direct synchronizer edge $group:$src->$dst"}
}
close $ef

# Measured register-to-register timing with real input-buffer/clock placement.
set regs [all_registers -clock board_clk_100mhz]
set setup [get_timing_paths -delay_type max -max_paths 1 -from $regs -to $regs]
set hold [get_timing_paths -delay_type min -max_paths 1 -from $regs -to $regs]
set f [open [file join $out internal_metrics.tsv] w]
puts $f "key\tvalue"
puts $f "register_count\t[llength $regs]"
puts $f "setup_path_count\t[llength $setup]"
puts $f "hold_path_count\t[llength $hold]"
if {[llength $setup]} { puts $f "setup_slack_ns\t[get_property SLACK [lindex $setup 0]]" }
if {[llength $hold]} { puts $f "hold_slack_ns\t[get_property SLACK [lindex $hold 0]]" }
close $f

# An explicit timing-exceptions file is intentionally absent. Physical async RX and
# reset signals have no fabricated arrival requirements. These are open signoff items.
set f [open [file join $out IMPLEMENTATION_COMPLETE] w]
puts $f "Phase 17 routed candidate. Config properties proposed per Rev C schematic; physical board, external timing and CDC are NOT VERIFIED."
close $f
puts "PHASE17: Config-property routed candidate complete; external I/O, CDC, reset, board identity remain OPEN. No bitstream."
exit
