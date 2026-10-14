# Phase 20: READ-ONLY explicit pin/segment reset-path trace of accepted Phase 17 DCP.
# Never modify checkpoint, add timing constraints, or claim physical reset signoff.
# vivado -mode batch -source scripts/phase20_exact_pin_trace.tcl -tclargs <post_route.dcp> <new_dir>
if {$argc != 2} {error "Expected Phase 17 checkpoint and fresh evidence directory"}
lassign $argv dcp out
set dcp [file normalize $dcp]
set out [file normalize $out]
if {![file isfile $dcp]} {error "Missing routed checkpoint: $dcp"}
if {[file exists $out]} {error "Refusing overwrite: $out"}
file mkdir $out
open_checkpoint $dcp
if {[get_property PART [current_project]] ne "xc7a100tcsg324-1"} {error "Unexpected FPGA part"}
if {[current_design] ni {checkpoint_post_route faultscope_uart_top}} {error "Unexpected top"}
if {[llength [get_clocks -quiet board_clk_100mhz]] != 1} {error "Missing expected clock"}
if {abs(double([get_property PERIOD [get_clocks board_clk_100mhz]])-10.0) > 0.00001} {error "Wrong clock period"}
if {[get_property CFGBVS [current_design]] ne "VCCO"} {error "Missing CFGBVS"}
if {abs(double([get_property CONFIG_VOLTAGE [current_design]])-3.3) > 0.00001} {error "Missing config voltage"}

proc p20pin {c refpin} {
    if {[llength $c] != 1} {error "Missing unique cell for pin $refpin"}
    set p [get_pins -quiet -of_objects $c -filter "REF_PIN_NAME == $refpin"]
    if {[llength $p] != 1} {error "Missing/ambiguous $refpin on [get_property NAME $c]"}
    return [lindex $p 0]
}
proc p20cell {name expected} {
    set c [get_cells -quiet $name]
    if {[llength $c] != 1 || [get_property REF_NAME $c] ne $expected} {error "Wrong/missing primitive: $name expected $expected"}
    return [lindex $c 0]
}
proc p20prop {obj field} {
    if {[catch {get_property $field $obj} val] || $val eq ""} {return "-"}
    return [string map [list "\t" " " "\r" " " "\n" " "] $val]
}
proc p20netnames {obj} {
    set names {}
    foreach n [get_nets -quiet -segments -of_objects $obj] {lappend names [p20prop $n NAME]}
    return [lsort -unique $names]
}
proc p20join {items} {if {![llength $items]} {return "-"}; return [join $items ","]}
proc p20shared {left right} {
    set a [p20netnames $left]
    set b [p20netnames $right]
    set both {}
    foreach n $a {if {[lsearch -exact $b $n] >= 0} {lappend both $n}}
    return [lsort -unique $both]
}
# Count ONLY leaf physical primitive output drivers, not hierarchical module pins.
# A module boundary fs_reset_sync port may share the hierarchical net without being
# a separate electrical driver; do not count it as one.
proc p20drivers {sink} {
    set seen {}
    foreach n [get_nets -quiet -segments -of_objects $sink] {
        foreach p [get_pins -quiet -of_objects $n -filter {DIRECTION == OUT}] {
            set c [get_cells -quiet -of_objects $p]
            if {[llength $c] != 1} {continue}
            set ref [p20prop $c REF_NAME]
            if {![regexp {^(IBUF[A-Z0-9_]*|LUT[1-6]|FD[A-Z0-9_]+|INV|BUF[A-Z0-9_]*)$} $ref]} {continue}
            lappend seen "[p20prop $p NAME]|$ref"
        }
    }
    return [lsort -unique $seen]
}
set port [get_ports -quiet rst_n]
if {[llength $port] != 1} {error "rst_n physical input port missing"}
set buf [p20cell rst_n_IBUF_inst IBUF]
set resetLut [p20cell {u_reset_sync/release_pipe_q[2]_i_1} LUT1]
set rxLut [p20cell {u_reset_sync/FSM_sequential_state_q[1]_i_2} LUT1]
set release [p20cell {u_reset_sync/release_pipe_q_reg[2]} FDCE]
set stages [list \
    [p20cell {u_reset_sync/release_pipe_q_reg[0]} FDCE] \
    [p20cell {u_reset_sync/release_pipe_q_reg[1]} FDCE] \
    $release]
set rxStages [list \
    [p20cell {receiver/sync_q_reg[0]} FDPE] \
    [p20cell {receiver/sync_q_reg[1]} FDPE]]
foreach c $stages {
    if {[string toupper [get_property ASYNC_REG $c]] ni {TRUE 1}} {error "Lost reset ASYNC_REG"}
}
foreach c $rxStages {
    if {[string toupper [get_property ASYNC_REG $c]] ni {TRUE 1}} {error "Lost RX ASYNC_REG"}
}
set bi [p20pin $buf I]
set bo [p20pin $buf O]
set ri [p20pin $resetLut I0]
set ro [p20pin $resetLut O]
set qi [p20pin $release Q]
set ui [p20pin $rxLut I0]
set uo [p20pin $rxLut O]
set links [list \
    [list reset_port_to_ibuf $port $bi] \
    [list reset_ibuf_to_lut $bo $ri]]
set i 0
foreach c $stages {lappend links [list "reset_lut_to_clr$i" $ro [p20pin $c CLR]]; incr i}
lappend links [list release_q_to_lut $qi $ui]
set i 0
foreach c $rxStages {lappend links [list "release_lut_to_pre$i" $uo [p20pin $c PRE]]; incr i}

set f [open [file join $out context.tsv] w]
puts $f "key\tvalue"
foreach {k v} [list phase 20 scope post_route_read_only_pin_exact_trace part [get_property PART [current_project]] design [current_design] vivado_version [version -short] clock_name board_clk_100mhz clock_period_ns [get_property PERIOD [get_clocks board_clk_100mhz]] cfgbvs [get_property CFGBVS [current_design]] config_voltage [get_property CONFIG_VOLTAGE [current_design]]] {puts $f "$k\t$v"}
close $f
set f [open [file join $out lut_truth.tsv] w]
puts $f "role\tcell\tref_name\tinit\ti0_pin\to_pin\ttruth_status"
foreach {role c} [list reset $resetLut release $rxLut] {
    set init [p20prop $c INIT]
    set status "NOT_VERIFIED"
    if {$init eq "2'h1"} {set status "ONE_INPUT_INVERTER"}
    puts $f "$role\t[p20prop $c NAME]\t[p20prop $c REF_NAME]\t$init\t[p20prop [p20pin $c I0] NAME]\t[p20prop [p20pin $c O] NAME]\t$status"
}
close $f
set f [open [file join $out pin_edges.tsv] w]
puts $f "edge\tsrc_object\tdst_object\tsrc_direction\tdst_direction\tsrc_segments\tdst_segments\tshared_segments\tleaf_drivers\tdriver_count\tstatus"
foreach link $links {
    lassign $link label src dst
    set shared [p20shared $src $dst]
    set drv [p20drivers $dst]
    set sd [p20prop $src DIRECTION]
    set dd [p20prop $dst DIRECTION]
    set status "UNRESOLVED"
    if {$label eq "reset_port_to_ibuf"} {
        if {[llength $shared] && $sd eq "IN" && $dd eq "IN" && [llength $drv] == 0} {set status "PORT_TO_IBUF_DIRECT"}
    } else {
        set srcCell [get_cells -quiet -of_objects $src]
        if {[llength $srcCell] == 1} {
            set wanted "[p20prop $src NAME]|[p20prop $srcCell REF_NAME]"
            if {[llength $shared] && $sd eq "OUT" && $dd eq "IN" && $drv eq [list $wanted]} {
                set status "SEGMENT_AND_SINGLE_EXPECTED_DRIVER"
            }
        }
    }
    puts $f "$label\t[p20prop $src NAME]\t[p20prop $dst NAME]\t$sd\t$dd\t[p20join [p20netnames $src]]\t[p20join [p20netnames $dst]]\t[p20join $shared]\t[p20join $drv]\t[llength $drv]\t$status"
}
close $f
# Preserve Vivado's /C vs /Q fanin ambiguity as an explicit independent observation.
set f [open [file join $out preset_startpoints.tsv] w]
puts $f "rx_stage\tcontrol_pin\tstartpoint_class\tstartpoint_name\tstartpoint_ref_pin"
set i 0
foreach c $rxStages {
    set pre [p20pin $c PRE]
    set start [all_fanin -quiet -flat -startpoints_only -to $pre]
    if {![llength $start]} {puts $f "$i\t[p20prop $pre NAME]\t-\t-\t-"}
    foreach item $start {puts $f "$i\t[p20prop $pre NAME]\t[p20prop $item CLASS]\t[p20prop $item NAME]\t[p20prop $item REF_PIN_NAME]"}
    incr i
}
close $f
check_timing -verbose -file [file join $out check_timing.rpt]
report_methodology -file [file join $out methodology.rpt]
puts "PHASE20: Explicit pin evidence collected. Reset electrical polarity/board signoff NOT VERIFIED."
exit
