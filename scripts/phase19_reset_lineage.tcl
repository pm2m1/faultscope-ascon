# Phase 19 exploratory, READ-ONLY routed reset source and pin polarity audit.
# Vivado batch -source scripts/phase19_reset_lineage.tcl -tclargs <Phase17 DCP> <fresh output directory>
# Source identities come from Vivado pin/port objects, never from a net's misleading name.
if {$argc != 2} {error "Expected Phase 17 DCP and NEW output directory"}
lassign $argv dcp out
set dcp [file normalize $dcp]
set out [file normalize $out]
if {![file isfile $dcp]} {error "Missing Phase 17 DCP: $dcp"}
if {[file exists $out]} {error "Refusing to overwrite existing Phase 19 evidence: $out"}
file mkdir $out
open_checkpoint $dcp
if {[get_property PART [current_project]] ne "xc7a100tcsg324-1"} {error "Wrong FPGA part"}
if {[current_design] ni {checkpoint_post_route faultscope_uart_top}} {error "Wrong routed top"}
if {[lsort [get_ports]] ne [lsort {clk rst_n uart_rx_i uart_tx_o led_busy_o led_alarm_o}]} {error "Board ports changed"}
if {[llength [get_clocks -quiet board_clk_100mhz]] != 1} {error "Clock missing"}
if {abs(double([get_property PERIOD [get_clocks board_clk_100mhz]])-10.0)>0.00001} {error "Wrong board clock"}
if {[get_property CFGBVS [current_design]] ne "VCCO"} {error "CFGBVS missing"}
if {abs(double([get_property CONFIG_VOLTAGE [current_design]])-3.3)>0.00001} {error "Configuration voltage missing"}

proc p19pin {cell refpin} {
    set match [get_pins -quiet -of_objects $cell -filter "REF_PIN_NAME == $refpin"]
    if {[llength $match] != 1} {error "Missing/ambiguous $refpin on [get_property NAME $cell]"}
    return [lindex $match 0]
}
proc p19nets {obj} {
    return [get_nets -quiet -segments -of_objects $obj]
}
proc p19shared {x y} {
    set left {}
    foreach n [p19nets $x] {lappend left [get_property NAME $n]}
    foreach n [p19nets $y] {
        set name [get_property NAME $n]
        if {[lsearch -exact $left $name] >= 0} {return $name}
    }
    return "-"
}
proc p19safe {obj field} {
    if {[catch {get_property $field $obj} val] || $val eq ""} {return "-"}
    return [string map [list "\t" " " "\n" " " "\r" " "] $val]
}
proc p19unique_names {items} {
    set names {}
    foreach item $items {lappend names [p19safe $item NAME]}
    return [join [lsort -unique $names] ","]
}

set f [open [file join $out context.tsv] w]
puts $f "key\tvalue"
foreach {k v} [list phase 19 scope post_route_read_only_reset_lineage part [get_property PART [current_project]] design [current_design] vivado_version [version -short] clock_period_ns [get_property PERIOD [get_clocks board_clk_100mhz]] cfgbvs [get_property CFGBVS [current_design]] config_voltage [get_property CONFIG_VOLTAGE [current_design]]] {
    puts $f "$k\t$v"
}
close $f

# Verify the physical active-low reset comes through exactly one FPGA input buffer.
set resetPort [get_ports {rst_n}]
set matches {}
foreach buf [get_cells -quiet -hierarchical -filter {REF_NAME =~ IBUF*}] {
    set pi [get_pins -quiet -of_objects $buf -filter {REF_PIN_NAME == I}]
    if {[llength $pi] == 1 && [p19shared $resetPort $pi] ne "-"} {lappend matches $buf}
}
set f [open [file join $out reset_input.tsv] w]
puts $f "port\tbuffer_count\tbuffer_cell\tbuffer_ref\tinput_net\toutput_net"
set bufcount [llength $matches]
if {$bufcount == 1} {
    set buf [lindex $matches 0]
    set ip [p19pin $buf I]
    set op [p19pin $buf O]
    set innet [p19shared $resetPort $ip]
    set outn [p19unique_names [p19nets $op]]
    puts $f "rst_n\t$bufcount\t[p19safe $buf NAME]\t[p19safe $buf REF_NAME]\t$innet\t$outn"
} else {
    puts $f "rst_n\t$bufcount\t-\t-\t-\t-"
}
close $f

# STARTPOINTS are actual pin/port objects. The observed NET NAME is not a driver identity.
set roots [open [file join $out startpoints.tsv] w]
puts $roots "sink_group\tsink_stage\tsink_cell\tstartpoint_class\tstartpoint_name\tstartpoint_ref_pin"
set controls [open [file join $out controls.tsv] w]
puts $controls "group\tstage\tcell\tprimitive\tcontrol_pin\tactive_level\tcontrol_net_segments\tstartpoint_count\tstartpoint_names\tstatus"
set drivers [open [file join $out control_drivers.tsv] w]
puts $drivers "group\tstage\tcontrol_pin\tdriver_kind\tdriver_name\tdriver_cell_ref\tdriver_ref_pin\tdriver_init"
set cells [open [file join $out comb_cone.tsv] w]
puts $cells "group\tstage\tcell\tref_name\tinit"
set resetNames {{u_reset_sync/release_pipe_q_reg[0]} {u_reset_sync/release_pipe_q_reg[1]} {u_reset_sync/release_pipe_q_reg[2]}}
set rxNames {{receiver/sync_q_reg[0]} {receiver/sync_q_reg[1]}}
foreach group {reset rx} {
    if {$group eq "reset"} {set names $resetNames; set ref FDCE; set pinName CLR} else {set names $rxNames; set ref FDPE; set pinName PRE}
    set index 0
    foreach name $names {
        set ff [get_cells -quiet $name]
        if {[llength $ff] != 1} {error "Missing/duplicate $name"}
        if {[get_property REF_NAME $ff] ne $ref} {error "Unexpected primitive on $name"}
        if {[string toupper [get_property ASYNC_REG $ff]] ni {TRUE 1}} {error "Lost ASYNC_REG: $name"}
        set control [p19pin $ff $pinName]
        set netobjs [p19nets $control]
        set netNames [p19unique_names $netobjs]
        if {$netNames eq ""} {set netNames "-"}
        set startobjs [all_fanin -quiet -flat -startpoints_only -to $control]
        set rootNames [p19unique_names $startobjs]
        if {$rootNames eq ""} {set rootNames "-"}
        set count [llength $startobjs]
        foreach start $startobjs {
            puts $roots "$group\t$index\t$name\t[p19safe $start CLASS]\t[p19safe $start NAME]\t[p19safe $start REF_PIN_NAME]"
        }
        set directPins [get_pins -quiet -of_objects $netobjs -filter {DIRECTION == OUT}]
        set directPorts [get_ports -quiet -of_objects $netobjs -filter {DIRECTION == IN}]
        foreach dp $directPins {
            set drvCell [get_cells -quiet -of_objects $dp]
            if {[llength $drvCell] != 1} {error "Driver pin has no unique cell: [get_property NAME $dp]"}
            puts $drivers "$group\t$index\t$pinName\tPIN\t[p19safe $dp NAME]\t[p19safe $drvCell REF_NAME]\t[p19safe $dp REF_PIN_NAME]\t[p19safe $drvCell INIT]"
        }
        foreach dp $directPorts {
            puts $drivers "$group\t$index\t$pinName\tPORT\t[p19safe $dp NAME]\t-\t-\t-"
        }
        if {![llength $directPins] && ![llength $directPorts]} {puts $drivers "$group\t$index\t$pinName\tNONE\t-\t-\t-\t-"}
        # Report the combinational cone and LUT INIT values for subsequent manual polarity tracing.
        set cone [all_fanin -quiet -flat -only_cells -to $control]
        foreach c $cone {
            set cref [p19safe $c REF_NAME]
            if {[string match {LUT*} $cref] || $cref in {INV BUF IBUF IBUFCTRL}} {
                puts $cells "$group\t$index\t[p19safe $c NAME]\t$cref\t[p19safe $c INIT]"
            }
        }
        # Do not say polarity verified from path reachability alone.
        set state "CONNECTED_REVIEW_REQUIRED"
        if {$netNames eq "-" || $count == 0 || (![llength $directPins] && ![llength $directPorts])} {
            set state "SOURCE_NOT_RESOLVED"
        }
        puts $controls "$group\t$index\t$name\t$ref\t$pinName\tHIGH\t$netNames\t$count\t$rootNames\t$state"
        incr index
    }
}
close $controls
close $roots
close $drivers
close $cells

# Inspect how the release stage reaches the RX asynchronous presets and other consumers.
set release [get_cells {u_reset_sync/release_pipe_q_reg[2]}]
set q [p19pin $release Q]
set ends [all_fanout -quiet -flat -endpoints_only -only_cells -from $q]
set uf [open [file join $out release_fanout.tsv] w]
puts $uf "source_cell\tendpoint_count\trx_stage0_in_endpoints\trx_stage1_in_endpoints\tendpoint_names"
set endpointNames {}
foreach c $ends {lappend endpointNames [p19safe $c NAME]}
set list [join [lsort -unique $endpointNames] ","]
if {$list eq ""} {set list "-"}
set found0 [expr {[lsearch -exact $endpointNames {receiver/sync_q_reg[0]}] >= 0 ? 1 : 0}]
set found1 [expr {[lsearch -exact $endpointNames {receiver/sync_q_reg[1]}] >= 0 ? 1 : 0}]
puts $uf "u_reset_sync/release_pipe_q_reg\[2\]\t[llength $ends]\t$found0\t$found1\t$list"
close $uf

check_timing -verbose -file [file join $out check_timing.rpt]
report_methodology -file [file join $out methodology.rpt]
puts "PHASE19: Physical reset input and async controls surveyed. Source polarity requires evidence review; no constraints or netlist modified."
exit
