# Phase 22 — read-only exact timing-path report binding and board I/O inventory.
# Input: the accepted Phase 17 routed checkpoint. No XDC, timing constraint,
# implementation, checkpoint or bitstream mutations are permitted.
# Each timing report is created from the SAME timing-path object returned by
# its explicit get_timing_paths query; do not mix Tcl lists of pin collections.
if {$argc != 2} {error "Expected accepted Phase 17 DCP and fresh output directory"}
lassign $argv dcp out
set dcp [file normalize $dcp]
set out [file normalize $out]
if {![file isfile $dcp]} {error "Missing routed DCP: $dcp"}
if {[file exists $out]} {error "Refusing to overwrite Phase 22 evidence: $out"}
file mkdir $out
open_checkpoint $dcp
if {[get_property PART [current_project]] ne "xc7a100tcsg324-1"} {error "Wrong device"}
if {[current_design] ni {checkpoint_post_route faultscope_uart_top}} {error "Wrong design"}
if {[lsort [get_ports]] ne [lsort {clk rst_n uart_rx_i uart_tx_o led_busy_o led_alarm_o}]} {error "Unexpected top interface"}
set clock [get_clocks -quiet board_clk_100mhz]
if {[llength $clock] != 1} {error "Missing/duplicate 100 MHz board clock"}
if {abs(double([get_property PERIOD $clock]) - 10.000)>0.00001} {error "Incorrect clock period"}
if {[get_property CFGBVS [current_design]] ne "VCCO"} {error "Unexpected CFGBVS"}
if {abs(double([get_property CONFIG_VOLTAGE [current_design]])-3.3)>0.00001} {error "Unexpected configuration voltage"}
proc p22pin {name pinref primitive} {
    set cell [get_cells -quiet $name]
    if {[llength $cell] != 1 || [get_property REF_NAME $cell] ne $primitive} {error "Unexpected cell $name"}
    set pins [get_pins -quiet -of_objects $cell -filter "REF_PIN_NAME == $pinref"]
    if {[llength $pins] != 1} {error "Unexpected pin $name/$pinref"}
    return [lindex $pins 0]
}
set release_q [p22pin {u_reset_sync/release_pipe_q_reg[2]} Q FDCE]
set f [open [file join $out context.tsv] w]
puts $f "key\tvalue"
foreach {k v} [list phase 22 scope post_route_read_only_path_binding part [get_property PART [current_project]] design [current_design] vivado_version [version -short] clock_name board_clk_100mhz clock_period_ns [get_property PERIOD $clock] cfgbvs [get_property CFGBVS [current_design]] config_voltage [get_property CONFIG_VOLTAGE [current_design]] external_delay_model NOT_QUALIFIED board_revision PROVISIONAL physical_reset_signoff NOT_VERIFIED] {
    puts $f "$k\t$v"
}
close $f
# Report actual implemented port assignments; these alone do not prove physical
# board revision or timing budgets. A master XDC is a pin map, NOT a delay spec.
set f [open [file join $out ports.tsv] w]
puts $f "port\tdirection\tpackage_pin\tiostandard"
foreach name {clk rst_n uart_rx_i uart_tx_o led_busy_o led_alarm_o} {
    set p [get_ports -quiet $name]
    if {[llength $p] != 1} {error "Unknown board port: $name"}
    puts $f "$name\t[get_property DIRECTION $p]\t[get_property PACKAGE_PIN $p]\t[get_property IOSTANDARD $p]"
}
close $f
# Ten independently selected paths. This avoids a prior Phase 21 artifact:
# a grouped report_timing command header contained last-element Tcl arguments.
# get_timing_paths can return source /C for recovery/removal even when explicit
# physical net connectivity is from /Q. Preserve both and investigate later.
set f [open [file join $out path_bindings.tsv] w]
puts $f "group\tstage\tdelay_type\trequested_source\trequested_sink\tquery_state\tpath_count\tslack_ns\treport_file\treport_state"
set rst [get_ports -quiet rst_n]
set groups [list]
for {set i 0} {$i < 3} {incr i} {
    lappend groups [list reset $i $rst [p22pin "u_reset_sync/release_pipe_q_reg\[$i\]" CLR FDCE]]
}
for {set i 0} {$i < 2} {incr i} {
    lappend groups [list rx $i $release_q [p22pin "receiver/sync_q_reg\[$i\]" PRE FDPE]]
}
foreach item $groups {
    lassign $item group stage src dst
    foreach delay {max min} {
        set s [get_property NAME $src]
        set d [get_property NAME $dst]
        set report_name "path_${group}${stage}_${delay}.rpt"
        set path_file [file join $out $report_name]
        set state NO_PATH_REPORTED
        set count 0
        set slack -
        set report_state NO_PATH_REPORTED
        if {[catch {get_timing_paths -quiet -from $src -to $dst -delay_type $delay -max_paths 1} paths]} {
            set state QUERY_ERROR
            set report_state QUERY_ERROR
            set h [open $path_file w]
            puts $h "QUERY_ERROR during path selection: $paths"
            close $h
        } else {
            set count [llength $paths]
            if {$count == 1} {
                set p [lindex $paths 0]
                set raw [string trim [get_property SLACK $p]]
                if {$raw eq "" || [string tolower $raw] in {inf +inf -inf nan}} {
                    set state PATH_REPORTED_SLACK_UNAVAILABLE
                } else {
                    set state PATH_REPORTED
                    set slack $raw
                }
                # Per AMD UG835, -of_objects binds the textual report to this
                # exact path object; it must NOT also use -from/-to/-delay_type.
                if {[catch {report_timing -of_objects $p -file $path_file} message]} {
                    set report_state REPORT_QUERY_ERROR
                    set h [open $path_file w]
                    puts $h "REPORT_QUERY_ERROR: $message"
                    close $h
                } else {
                    set report_state REPORT_WRITTEN
                }
            } elseif {$count == 0} {
                set h [open $path_file w]
                puts $h "NO_PATH_REPORTED for $group $stage $delay: $s to $d"
                close $h
            } else {
                error "Unexpected multiple timing paths at $group $stage $delay"
            }
        }
        puts $f "$group\t$stage\t$delay\t$s\t$d\t$state\t$count\t$slack\t$report_name\t$report_state"
    }
}
close $f
check_timing -verbose -file [file join $out check_timing.rpt]
report_methodology -file [file join $out methodology.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 3 -file [file join $out timing_summary.rpt]
puts "PHASE22: ten path-bound reports and board pin inventory collected for review; no physical signoff."
exit
