# Board clock and PLL output clocks.
create_clock -name sys_clk -period 20.000 [get_ports { clk }]
derive_pll_clocks
derive_clock_uncertainty
# LEDs are static indicators; exclude them from I/O timing.
set_false_path -to [get_ports { led[*] }]
