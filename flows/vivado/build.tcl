lassign $argv design board_dir part cdc_xdc out_dir opts_tcl
set root [file dirname [file dirname [file dirname [file normalize [info script]]]]]
set rtl [expr {[file isdirectory $design] ? [file join $design rtl] : [file join $root designs $design rtl]}]
set design [file tail $design]

create_project -force $design $out_dir -part $part
add_files [concat [glob [file join $rtl *.v]] [file join $board_dir clk_gen.v]]
source [file join $board_dir clk_wiz.tcl]
add_files -fileset constrs_1 [list [file join $board_dir pins.xdc] [file join $board_dir sync.xdc] $cdc_xdc]
set_property USED_IN_SYNTHESIS false [get_files $cdc_xdc]
set_property top board_top [current_fileset]
if {$opts_tcl ne "" && $opts_tcl ne "-"} { source $opts_tcl }

launch_runs synth_1 -jobs 4
wait_on_run synth_1
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "impl_1 failed" }

open_run impl_1
set rpt [file join $out_dir reports]
file mkdir $rpt
report_utilization       -file [file join $rpt utilization.rpt]
report_timing_summary    -file [file join $rpt timing_summary.rpt]
report_clock_interaction -file [file join $rpt clock_interaction.rpt]
report_cdc -details      -file [file join $rpt cdc.rpt]
report_bus_skew          -file [file join $rpt bus_skew.rpt]
report_drc               -file [file join $rpt drc.rpt]
write_bitstream -force -mask_file [file join $out_dir $design.bit]
close_project
