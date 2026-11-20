# xcu250-figd2104-2L-e, build only (no board is programmed). Used by the RQ5 logic-size
# experiment to build designs with more than one million LUTs. Pins are general-purpose pins
# of HP bank 64 listed by Vivado (get_package_pins); the clock pin is the P side of a global-clock pair (IO_L11P_T1U_N8_GC_64).
set_property -dict { PACKAGE_PIN AW20 IOSTANDARD LVCMOS18 } [get_ports { clk }]
set_property -dict { PACKAGE_PIN AL21 IOSTANDARD LVCMOS18 } [get_ports { led[0] }]
set_property -dict { PACKAGE_PIN AP21 IOSTANDARD LVCMOS18 } [get_ports { led[1] }]
set_property -dict { PACKAGE_PIN AL19 IOSTANDARD LVCMOS18 } [get_ports { led[2] }]
set_property -dict { PACKAGE_PIN AN22 IOSTANDARD LVCMOS18 } [get_ports { led[3] }]
set_false_path -to [get_ports { led[*] }]
