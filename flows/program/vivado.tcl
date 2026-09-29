lassign $argv bit msk rbd
open_hw_manager
connect_hw_server
open_hw_target
set dev [lindex [get_hw_devices xc7z020*] 0]
current_hw_device $dev
puts "TARGET [current_hw_target]"
puts "DEVICE [get_property PART $dev] IDCODE [get_property IDCODE $dev]"
if {$msk eq "-"} {
    create_hw_bitstream -hw_device $dev $bit
} else {
    create_hw_bitstream -hw_device $dev -mask $msk $bit
}
program_hw_devices $dev
catch {puts "DONE_PIN [get_property REGISTER.CONFIG_STATUS.BIT14_DONE_PIN $dev]"}
if {$msk eq "-"} {
    puts "VERIFY NOT_RUN: no mask file"
} else {
    verify_hw_devices $dev
    readback_hw_device -force -readback_file $rbd $dev
}
close_hw_target
disconnect_hw_server
close_hw_manager
