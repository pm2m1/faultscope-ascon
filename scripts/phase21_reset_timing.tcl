# Phase 21: READ-ONLY reset timing modeling and recovery/removal observability.
# Use accepted Phase 17 post-route checkpoint only. Never generate a bitstream,
# introduce input/output delays or exceptions, or equate clock pulse checks
# with minimum reset pulse-width qualification.
# vivado -mode batch -source scripts/phase21_reset_timing.tcl -tclargs <post_route.dcp> <fresh_output_dir>
if {$argc != 2} {error "Expected Phase 17 DCP and new output directory"}
lassign $argv dcp out
set dcp [file normalize $dcp]
set out [file normalize $out]
if {![file isfile $dcp]} {error "Missing Phase 17 routed checkpoint: $dcp"}
if {[file exists $out]} {error "Refusing overwrite: $out"}
file mkdir $out
open_checkpoint $dcp
if {[get_property PART [current_project]] ne "xc7a100tcsg324-1"} {error "Unexpected FPGA part"}
if {[current_design] ni {checkpoint_post_route faultscope_uart_top}} {error "Unexpected design"}
if {[lsort [get_ports]] ne [lsort {clk rst_n uart_rx_i uart_tx_o led_busy_o led_alarm_o}]} {error "Top-level interface changed"}
set clocks [get_clocks -quiet board_clk_100mhz]
if {[llength $clocks] != 1} {error "Exactly one named board clock required"}
if {abs(double([get_property PERIOD $clocks])-10.0)>0.00001} {error "Wrong board clock period"}
if {[get_property CFGBVS [current_design]] ne "VCCO"} {error "Unexpected CFGBVS"}
if {abs(double([get_property CONFIG_VOLTAGE [current_design]])-3.3)>0.00001} {error "Unexpected configuration voltage"}
proc p21pin {name ref expected} {
    set cell [get_cells -quiet $name]
    if {[llength $cell] != 1 || [get_property REF_NAME $cell] ne $expected} {
        error "Missing/wrong mapped register $name"
    }
    set pin [get_pins -quiet -of_objects $cell -filter "REF_PIN_NAME == $ref"]
    if {[llength $pin] != 1} {error "Missing/wrong control pin $name/$ref"}
    return [lindex $pin 0]
}
set port [get_ports -quiet rst_n]
if {[llength $port] != 1} {error "Missing external asynchronous reset port"}
set releaseQ [p21pin {u_reset_sync/release_pipe_q_reg[2]} Q FDCE]
set endpoints [list]
for {set i 0} {$i < 3} {incr i} {
    set cell "u_reset_sync/release_pipe_q_reg\[$i\]"
    lappend endpoints [list reset "$i" $port [p21pin $cell CLR FDCE]]
}
for {set i 0} {$i < 2} {incr i} {
    set cell "receiver/sync_q_reg\[$i\]"
    lappend endpoints [list rx "$i" $releaseQ [p21pin $cell PRE FDPE]]
}
set f [open [file join $out context.tsv] w]
puts $f "key\tvalue"
foreach {k v} [list phase 21 scope post_route_read_only_reset_timing part [get_property PART [current_project]] design [current_design] vivado_version [version -short] clock_name board_clk_100mhz clock_period_ns [get_property PERIOD $clocks] cfgbvs [get_property CFGBVS [current_design]] config_voltage [get_property CONFIG_VOLTAGE [current_design]] reset_external_delay_qualification NOT_VERIFIED board_oscillator_startup NOT_VERIFIED board_reset_pulse_width NOT_VERIFIED] {puts $f "$k\t$v"}
close $f
# Path observations, NOT timing signoff. A missing path has NOT passed a check.
set f [open [file join $out path_observations.tsv] w]
puts $f "group\tstage\tsource\tsink\tdelay_type\tquery_state\tpath_count\tslack_ns"
foreach ep $endpoints {
    lassign $ep group stage src sink
    foreach delay {max min} {
        set s [get_property NAME $src]
        set d [get_property NAME $sink]
        set n 0
        set slack "-"
        set state NO_PATH_REPORTED
        # Catch the tooling query without changing any timing constraints.
        if {[catch {get_timing_paths -quiet -from $src -to $sink -delay_type $delay -max_paths 1} paths]} {
            set state QUERY_ERROR
        } else {
            set n [llength $paths]
            if {$n == 1} {
                set raw_slack [get_property SLACK [lindex $paths 0]]
                if {[string trim $raw_slack] eq ""} {
                    # External rst_n has no input-delay model. A reported
                    # topology is not a finite timing check or a PASS.
                    set slack "-"
                    set state PATH_REPORTED_SLACK_UNAVAILABLE
                } else {
                    set slack $raw_slack
                    set state PATH_REPORTED
                }
            } elseif {$n > 1} {error "Unexpected multiple queried paths for $group $stage $delay"}
        }
        puts $f "$group\t$stage\t$s\t$d\t$delay\t$state\t$n\t$slack"
    }
}
close $f
# Textual reports retain every modeling limitation and queried timing path.
check_timing -verbose -file [file join $out check_timing.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 3 -file [file join $out timing_summary.rpt]
report_methodology -file [file join $out methodology.rpt]
# IMPORTANT: this is clock-network pulse width ONLY, not rst_n external pulse width.
report_pulse_width -clocks $clocks -file [file join $out clock_pulse_width.rpt]
set resetPins [list]
set prePins [list]
foreach ep $endpoints {
    lassign $ep group stage src sink
    if {$group eq "reset"} {lappend resetPins $sink} else {lappend prePins $sink}
}
foreach {name from to} [list reset_from_port $port $resetPins release_to_preset $releaseQ $prePins] {
    foreach delay {max min} {
        set outReport [file join $out "${name}_${delay}.rpt"]
        if {[catch {report_timing -from $from -to $to -delay_type $delay -max_paths 3 -file $outReport} err]} {
            set ff [open $outReport w]
            puts $ff "QUERY_ERROR: $err"
            close $ff
        }
    }
}
puts "PHASE21: read-only async reset timing observations collected; physical reset timing remains NOT VERIFIED."
exit
