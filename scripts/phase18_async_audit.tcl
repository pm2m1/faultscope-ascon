# Phase 18: READ-ONLY examination of the already-routed Phase 17 candidate.
# Usage: vivado -mode batch -source scripts/phase18_async_audit.tcl -tclargs <phase17_post_route.dcp> <new_output_directory>
# No bitstream, no timing-exception mutation, no constraint additions and no MTBF claim.
if {$argc != 2} {error "Expected Phase 17 DCP and fresh output directory"}
lassign $argv dcp out
set dcp [file normalize $dcp]
set out [file normalize $out]
if {![file isfile $dcp]} {error "Missing routed candidate DCP: $dcp"}
if {[file exists $out]} {error "Refusing to overwrite existing evidence directory: $out"}
file mkdir $out
open_checkpoint $dcp
if {[get_property PART [current_project]] ne "xc7a100tcsg324-1"} {error "Unexpected routed FPGA part"}
if {[current_design] ni {checkpoint_post_route faultscope_uart_top}} {error "Unexpected design"}
if {[lsort [get_ports]] ne [lsort {clk rst_n uart_rx_i uart_tx_o led_busy_o led_alarm_o}]} {error "Top-level port mismatch"}
if {[llength [get_clocks -quiet board_clk_100mhz]] != 1} {error "Missing board clock"}
if {abs(double([get_property PERIOD [get_clocks board_clk_100mhz]])-10.0)>0.00001} {error "Unexpected clock period"}
if {[get_property CFGBVS [current_design]] ne "VCCO"} {error "CFGBVS lost"}
if {abs(double([get_property CONFIG_VOLTAGE [current_design]])-3.3)>0.00001} {error "CONFIG_VOLTAGE lost"}

# A net may have hierarchical segments. Compare all segment names, not a single alias.
proc p18nets {obj} {
    set n [get_nets -quiet -segments -of_objects $obj]
    set names {}
    foreach item $n {lappend names [get_property NAME $item]}
    return [lsort -unique $names]
}
proc p18shared {left right} {
    set a [p18nets $left]
    set b [p18nets $right]
    foreach n $a {if {[lsearch -exact $b $n] >= 0} {return $n}}
    return "-"
}
proc p18pin {cell refpin} {
    set p [get_pins -quiet -of_objects $cell -filter "REF_PIN_NAME == $refpin"]
    if {[llength $p] != 1} {error "Missing/ambiguous pin $refpin for [get_property NAME $cell]"}
    return [lindex $p 0]
}

set f [open [file join $out context.tsv] w]
puts $f "key\tvalue"
puts $f "phase\t18"
puts $f "scope\tpost_route_read_only_async_boundary"
puts $f "part\t[get_property PART [current_project]]"
puts $f "design\t[current_design]"
puts $f "vivado_version\t[version -short]"
puts $f "clock_name\tboard_clk_100mhz"
puts $f "clock_period_ns\t[get_property PERIOD [get_clocks board_clk_100mhz]]"
puts $f "cfgbvs\t[get_property CFGBVS [current_design]]"
puts $f "config_voltage\t[get_property CONFIG_VOLTAGE [current_design]]"
close $f

set reset_names {
    {u_reset_sync/release_pipe_q_reg[0]}
    {u_reset_sync/release_pipe_q_reg[1]}
    {u_reset_sync/release_pipe_q_reg[2]}
}
set rx_names {
    {receiver/sync_q_reg[0]}
    {receiver/sync_q_reg[1]}
}
set f [open [file join $out stages.tsv] w]
puts $f "group\tstage\tcell\tref_name\tasync_reg\tloc\tbel\tasync_control_net"
foreach group {reset rx} {
    if {$group eq "reset"} {set nlist $reset_names} else {set nlist $rx_names}
    set idx 0
    foreach name $nlist {
        set ff [get_cells -quiet $name]
        if {[llength $ff] != 1} {error "Missing/duplicate mapped stage: $name"}
        set ref [get_property REF_NAME $ff]
        if {![string match "FD*" $ref]} {error "Wrong stage primitive: $name $ref"}
        if {[string toupper [get_property ASYNC_REG $ff]] ni {1 TRUE}} {error "ASYNC_REG missing: $name"}
        set loc [get_property LOC $ff]
        set bel [get_property BEL $ff]
        if {![string match "SLICE_X*" $loc] || $bel eq ""} {error "Unplaced/invalid stage $name"}
        if {$group eq "reset"} {
            # Reset pipe FFs must have a connected asynchronous-clear control.
            if {$ref ne "FDCE"} {error "Unexpected reset stage primitive: $name $ref"}
            set apin [p18pin $ff CLR]
        } else {
            # Receiver synchronizer is asynchronously preset to UART idle/high.
            if {$ref ne "FDPE"} {error "Unexpected RX stage primitive: $name $ref"}
            set apin [p18pin $ff PRE]
        }
        set cnets [p18nets $apin]
        if {![llength $cnets]} {error "Floating asynchronous control: $name"}
        puts $f "$group\t$idx\t$name\t$ref\t[get_property ASYNC_REG $ff]\t$loc\t$bel\t[lindex $cnets 0]"
        incr idx
    }
}
close $f

set f [open [file join $out interstage_timing.tsv] w]
puts $f "group\tfrom_stage\tto_stage\tshared_qd_net\tmax_slack_ns\tmin_slack_ns\tstatus"
foreach {group src dst} {reset 0 1 reset 1 2 rx 0 1} {
    if {$group eq "reset"} {set prefix "u_reset_sync/release_pipe_q_reg"} else {set prefix "receiver/sync_q_reg"}
    set ff0 [get_cells "$prefix\[$src\]"]
    set ff1 [get_cells "$prefix\[$dst\]"]
    set q [p18pin $ff0 Q]
    set d [p18pin $ff1 D]
    set net [p18shared $q $d]
    if {$net eq "-"} {error "Interstage Q/D connectivity failure: $group $src->$dst"}
    set maxp [get_timing_paths -quiet -delay_type max -from $q -to $d -max_paths 1]
    set minp [get_timing_paths -quiet -delay_type min -from $q -to $d -max_paths 1]
    if {[llength $maxp] != 1 || [llength $minp] != 1} {error "Missing interstage timed Q/D path: $group $src->$dst"}
    set ms [get_property SLACK [lindex $maxp 0]]
    set hs [get_property SLACK [lindex $minp 0]]
    if {![string is double -strict $ms] || ![string is double -strict $hs]} {error "Non-numeric interstage slack"}
    puts $f "$group\t$src\t$dst\t$net\t$ms\t$hs\tDIRECT_AND_TIMED"
}
close $f

# Validate physical UART input -> IBUF -> first synchronizer D, not directly into arbitrary RTL.
# The source port is asynchronous. Physical setup/hold and analog MTBF remain UNVERIFIED.
set rxport [get_ports uart_rx_i]
set rx0 [get_cells {receiver/sync_q_reg[0]}]
set rxd [p18pin $rx0 D]
set ibuf_match {}
foreach buf [get_cells -quiet -hierarchical -filter {REF_NAME =~ IBUF*}] {
    set ipin [get_pins -quiet -of_objects $buf -filter {REF_PIN_NAME == I}]
    set opin [get_pins -quiet -of_objects $buf -filter {REF_PIN_NAME == O}]
    if {[llength $ipin] != 1 || [llength $opin] != 1} {continue}
    if {[p18shared $rxport $ipin] ne "-"} {lappend ibuf_match $buf}
}
if {[llength $ibuf_match] != 1} {error "Expected precisely one RX input buffer"}
set rxbuf [lindex $ibuf_match 0]
set ibufout [p18pin $rxbuf O]
set ibufnet [p18shared $ibufout $rxd]
if {$ibufnet eq "-"} {error "UART RX port is not buffered directly to first synchronizer D"}
# Structural fanout from the first RX flop must terminate only at stage 1.
# An incidental bypass to UART decode logic would invalidate the two-stage boundary.
set endpoint_objs [all_fanout -quiet -flat -endpoints_only -only_cells -from [p18pin $rx0 Q]]
set rx_endpoints {}
foreach c $endpoint_objs {lappend rx_endpoints [get_property NAME $c]}
set rx_endpoints [lsort -unique $rx_endpoints]
if {$rx_endpoints ne [list {receiver/sync_q_reg[1]}]} {
    error "First RX synchronizer flop has unsafe sequential fanout: $rx_endpoints"
}
set f [open [file join $out async_input.tsv] w]
puts $f "port\tbuffer_cell\tbuffer_ref\tfirst_stage_cell\tbuffer_to_stage_net\tstatus"
puts $f "uart_rx_i\t[get_property NAME $rxbuf]\t[get_property REF_NAME $rxbuf]\treceiver/sync_q_reg\[0\]\t$ibufnet\tIBUF_TO_FIRST_STAGE_DIRECT"
close $f

# Preserve unsatisfied modeling gaps as visible diagnostics; never add delays/exceptions.
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing -delay_type max -from [get_cells {receiver/sync_q_reg[0]}] -to [get_cells {receiver/sync_q_reg[1]}] -max_paths 1 -file [file join $out rx_interstage_max.rpt]
report_timing -delay_type min -from [get_cells {receiver/sync_q_reg[0]}] -to [get_cells {receiver/sync_q_reg[1]}] -max_paths 1 -file [file join $out rx_interstage_min.rpt]
report_methodology -file [file join $out methodology.rpt]
report_cdc -details -file [file join $out cdc.rpt]
puts "PHASE18: Routed async-boundary structural evidence collected; no analog/board signoff or bitstream."
exit
