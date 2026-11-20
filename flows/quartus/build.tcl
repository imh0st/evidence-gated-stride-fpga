load_package flow
lassign $quartus(args) design board_dir device cdc_sdc out_dir opts_tcl
set root [file dirname [file dirname [file dirname [file normalize [info script]]]]]
set rtl [expr {[file isdirectory $design] ? [file join $design rtl] : [file join $root designs $design rtl]}]
set design [file tail $design]

proc relpath {target base} {
    set t [file split [file normalize $target]]
    set b [file split [file normalize $base]]
    set i 0
    while {$i < [llength $b] && $i < [llength $t] && [string equal -nocase [lindex $t $i] [lindex $b $i]]} { incr i }
    return [join [concat [lrepeat [expr {[llength $b] - $i}] ..] [lrange $t $i end]] /]
}

file mkdir $out_dir
set out_dir [file normalize $out_dir]
set cdc_sdc [file normalize $cdc_sdc]
set board_dir [file normalize $board_dir]
cd $out_dir
project_new $design -overwrite
set_global_assignment -name FAMILY "Cyclone 10 LP"
set_global_assignment -name DEVICE $device
set_global_assignment -name TOP_LEVEL_ENTITY board_top
foreach f [concat [glob [file join $rtl *.v]] [file join $board_dir clk_gen.v]] {
    set_global_assignment -name VERILOG_FILE [relpath $f $out_dir]
}
set_global_assignment -name SDC_FILE [relpath [file join $board_dir clocks.sdc] $out_dir]
set_global_assignment -name SDC_FILE [relpath $cdc_sdc $out_dir]
source [file join $board_dir pins.tcl]
source [file join $board_dir sync.tcl]
if {$opts_tcl ne "" && $opts_tcl ne "-"} { source $opts_tcl }
export_assignments

execute_flow -compile
project_close

if {[file exists [file join $board_dir flash.tcl]]} {
    source [file join $board_dir flash.tcl]
    qexec "quartus_cpf -c -d $flash_device -s $device $design.sof $design.jic"
}
