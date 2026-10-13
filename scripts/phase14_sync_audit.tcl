# Phase 14 READ-ONLY inspection of a routed Phase 13 UART checkpoint.
# Usage: vivado -mode batch -source scripts/phase14_sync_audit.tcl -tclargs <post_route.dcp> <output-directory>
# DO NOT write_checkpoint, route_design, set_property, or write_bitstream here.
if {$argc != 2} { error "Expected checkpoint and output directory" }
lassign $argv checkpoint out
set checkpoint [file normalize $checkpoint]
set out [file normalize $out]
if {![file isfile $checkpoint]} { error "Missing routed checkpoint: $checkpoint" }
file mkdir $out
open_checkpoint $checkpoint
# Vivado restores routed OOC checkpoints with a generated design name,
# commonly checkpoint_post_route, rather than the original RTL top name.
# Preserve the original expected hierarchy/port/stage checks below; do not
# infer the original RTL top from the session-local checkpoint design name.
set checkpoint_design [current_design]
if {$checkpoint_design ni {faultscope_uart_top checkpoint_post_route}} {
    error "Unrecognized routed checkpoint design name: $checkpoint_design"
}

proc prop_or_dash {object property} {
    if {[catch {get_property $property $object} result] || $result eq ""} {return "-"}
    return [string map [list "\t" " " "\n" " "] $result]
}

set cf [open [file join $out cells.tsv] w]
puts $cf "group\tstage\tcell\tref_name\tasync_reg\tshreg_extract\tloc\tbel"
array set observed {}
# Query all mapped flip-flop cells; stage name matches are deliberately narrow.
set ffs [get_cells -quiet -hierarchical -filter {REF_NAME =~ FD*}]
foreach cell $ffs {
    set name [get_property NAME $cell]
    set group ""; set stage ""
    if {[regexp {(^|/)u_reset_sync/release_pipe_q_reg\[([0-2])\](_[0-9]+)?$} $name dummy prefix index suffix]} {
        set group "reset"; set stage $index
    } elseif {[regexp {(^|/)receiver/sync_q_reg\[([0-1])\](_[0-9]+)?$} $name dummy prefix index suffix]} {
        set group "rx"; set stage $index
    }
    if {$group eq ""} {continue}
    set key "$group:$stage"
    lappend observed($key) $cell
    puts $cf [join [list $group $stage $name \
        [prop_or_dash $cell REF_NAME] [prop_or_dash $cell ASYNC_REG] \
        [prop_or_dash $cell SHREG_EXTRACT] [prop_or_dash $cell LOC] \
        [prop_or_dash $cell BEL]] "\t"]
}
close $cf

# Net-level checking detects unexpected logic between synchronizer stages.
# Report failure/unknown rather than guessing when Vivado can't resolve a net.
proc pin_nets {cell pin_name} {
    set pins [get_pins -quiet -of_objects $cell -filter "REF_PIN_NAME == $pin_name"]
    if {[llength $pins] != 1} { return {} }
    if {[catch {get_nets -quiet -segments -of_objects $pins} nets]} { return {} }
    set names {}
    foreach net $nets { lappend names [get_property NAME $net] }
    return [lsort -unique $names]
}
set ef [open [file join $out edges.tsv] w]
puts $ef "group\tfrom_stage\tto_stage\tfrom_cell\tto_cell\tnet_overlap\tstatus"
foreach {group last} {reset 2 rx 1} {
    for {set i 0} {$i < $last} {incr i} {
        set j [expr {$i+1}]
        set k1 "$group:$i"; set k2 "$group:$j"
        set src "-"; set dst "-"; set shared "-"; set status "NOT_VERIFIED"
        if {[info exists observed($k1)] && [info exists observed($k2)] && \
            [llength $observed($k1)] == 1 && [llength $observed($k2)] == 1} {
            set s [lindex $observed($k1) 0]
            set d [lindex $observed($k2) 0]
            set src [get_property NAME $s]; set dst [get_property NAME $d]
            set sn [pin_nets $s Q]
            set dn [pin_nets $d D]
            foreach n $sn {
                if {[lsearch -exact $dn $n] != -1} { set shared $n; set status "DIRECT"; break }
            }
        }
        puts $ef [join [list $group $i $j $src $dst $shared $status] "\t"]
    }
}
close $ef

set pf [open [file join $out ports.tsv] w]
puts $pf "port\tdirection"
foreach p [get_ports] {puts $pf "[get_property NAME $p]\t[prop_or_dash $p DIRECTION]"}
close $pf

set cx [open [file join $out context.tsv] w]
puts $cx "key\tvalue"
puts $cx "top\t[current_design]"
puts $cx "vivado_version\t[version -short]"
puts $cx "clock_count\t[llength [get_clocks -quiet core_clk]]"
if {[llength [get_clocks -quiet core_clk]] == 1} {
    puts $cx "period_ns\t[get_property PERIOD [get_clocks core_clk]]"
}
puts $cx "clock_source\t[prop_or_dash [get_ports clk] HD.CLK_SRC]"
puts $cx "scope\tOOC; external UART/reset timing and physical board CDC unverified"
close $cx

# Context reports are diagnostic and are NOT accepted as analog MTBF proof.
report_timing_summary -delay_type min_max -report_unconstrained -file [file join $out timing_summary.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
report_cdc -details -file [file join $out cdc.rpt]
puts "PHASE14: Inspection complete; use the fail-closed Python validator before claiming preservation."
exit
