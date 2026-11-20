lassign $argv design board_dir cdc_sdc out_dir opts_tcl
set root [file dirname [file dirname [file dirname [file normalize [info script]]]]]
set rtl [expr {[file isdirectory $design] ? [file join $design rtl] : [file join $root designs $design rtl]}]
set design [file tail $design]

new_project -location $out_dir -name $design -hdl VERILOG -family {PolarFireSoC} \
    -die {MPFS095T} -package {FCSG325} -speed {-1} -die_voltage {1.0} -part_range {EXT} \
    -adv_options {IO_DEFT_STD:LVCMOS 1.8V}
source [file join $board_dir pf_ccc.tcl]
foreach f [concat [glob [file join $rtl *.v]] [file join $board_dir clk_gen.v]] {
    import_files -hdl_source $f
}
build_design_hierarchy
set_root -module {board_top::work}

import_files -io_pdc [file join $board_dir pins.pdc]
derive_constraints_sdc
import_files -sdc $cdc_sdc
set cons "$out_dir/constraint"
set sdcs [list -file "$cons/board_top_derived_constraints.sdc" -file "$cons/[file tail $cdc_sdc]"]
organize_tool_files -tool {SYNTHESIZE}   -module {board_top::work} -input_type {constraint} {*}$sdcs
organize_tool_files -tool {PLACEROUTE}   -module {board_top::work} -input_type {constraint} \
    -file "$cons/io/pins.pdc" {*}$sdcs
organize_tool_files -tool {VERIFYTIMING} -module {board_top::work} -input_type {constraint} {*}$sdcs

if {$opts_tcl ne "" && $opts_tcl ne "-"} { source $opts_tcl }
run_tool -name {SYNTHESIZE}
run_tool -name {PLACEROUTE}
run_tool -name {VERIFYTIMING}
run_tool -name {GENERATEPROGRAMMINGDATA}
run_tool -name {GENERATEPROGRAMMINGFILE}
file mkdir "$out_dir/export"
export_prog_job -job_file_name $design -export_dir "$out_dir/export" \
    -bitstream_file_type {TRUSTED_FACILITY} -bitstream_file_components {FABRIC}
save_project
close_project
