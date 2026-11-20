# xcu25-ffvc1760-2L-e, build only (no board is programmed). Used by the RQ5 logic-size
# experiment to build designs larger than the Zynq-7020 holds. Pins are general-purpose pins
# of HP bank 64 listed by Vivado (get_package_pins); the clock pin is the P side of a global-clock pair (IO_L11P_T1U_N8_GC_64).
set_property -dict { PACKAGE_PIN AU21 IOSTANDARD LVCMOS18 } [get_ports { clk }]
set_property -dict { PACKAGE_PIN BB21 IOSTANDARD LVCMOS18 } [get_ports { led[0] }]
set_property -dict { PACKAGE_PIN AW21 IOSTANDARD LVCMOS18 } [get_ports { led[1] }]
set_property -dict { PACKAGE_PIN AR22 IOSTANDARD LVCMOS18 } [get_ports { led[2] }]
set_property -dict { PACKAGE_PIN AL20 IOSTANDARD LVCMOS18 } [get_ports { led[3] }]
set_false_path -to [get_ports { led[*] }]
