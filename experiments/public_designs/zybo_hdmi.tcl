# Build the Digilent Zybo Z7-20 HDMI demo (release 20/HDMI/2025.1-1) with Vivado 2025.2.
# Argument: the .xpr of the extracted hardware project. The IP of the block design is upgraded to 2025.2, every run
# is reset so that the build starts from the sources, and the reports and the bitstream with its
# readback mask are written next to the project and its implementation run.
open_project [lindex $argv 0]
puts "PART [get_property part [current_project]] BOARD [get_property board_part [current_project]]"
foreach bd [get_files -quiet *.bd] {
    open_bd_design $bd
    set cells [get_bd_cells -quiet -hierarchical -filter {TYPE == ip}]
    puts "IPNET cells [llength $cells]"
    catch { upgrade_ip $cells } msg
    puts "UPGRADE $msg"
    save_bd_design
    close_bd_design [current_bd_design]
    generate_target all [get_files $bd]
}
catch { upgrade_ip [get_ips] }
foreach r [get_runs] { reset_run $r }
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
puts "IMPL_STATUS [get_property STATUS [get_runs impl_1]]"
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "impl_1 failed" }

open_run impl_1
set rpt [file join [get_property DIRECTORY [current_project]] reports]
file mkdir $rpt
report_utilization    -file [file join $rpt utilization.rpt]
report_timing_summary -file [file join $rpt timing_summary.rpt]
set bit [lindex [glob [file join [get_property DIRECTORY [get_runs impl_1]] *.bit]] 0]
write_bitstream -force -mask_file $bit
close_project
