set_location_assignment PIN_E1  -to clk
set_instance_assignment -name IO_STANDARD "2.5 V" -to clk
set_location_assignment PIN_L14 -to led[0]
set_location_assignment PIN_K15 -to led[1]
set_location_assignment PIN_J14 -to led[2]
set_location_assignment PIN_J13 -to led[3]
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to led[*]
set_instance_assignment -name CURRENT_STRENGTH_NEW 8MA -to led[*]
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED"
