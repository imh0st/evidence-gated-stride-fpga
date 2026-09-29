# Digilent Zybo Z7-20 (XC7Z020-1CLG400C). Pins from Digilent Zybo-Z7-Master.xdc.
# The 125 MHz primary clock is created by the Clocking Wizard IP constraints.
set_property -dict { PACKAGE_PIN K17 IOSTANDARD LVCMOS33 } [get_ports { clk }]
set_property -dict { PACKAGE_PIN M14 IOSTANDARD LVCMOS33 } [get_ports { led[0] }]
set_property -dict { PACKAGE_PIN M15 IOSTANDARD LVCMOS33 } [get_ports { led[1] }]
set_property -dict { PACKAGE_PIN G14 IOSTANDARD LVCMOS33 } [get_ports { led[2] }]
set_property -dict { PACKAGE_PIN D18 IOSTANDARD LVCMOS33 } [get_ports { led[3] }]
# LEDs are static indicators; exclude them from I/O timing.
set_false_path -to [get_ports { led[*] }]
