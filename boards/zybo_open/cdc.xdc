# Clock constraints for the two FIFO domains (approved), open flow.
# nextpnr-xilinx reads create_clock but has no path-delay exceptions
# (set_max_delay, set_bus_skew, set_false_path are ignored with a message),
# so the Gray-pointer crossings cannot be bounded as in the vendor flows.
create_clock -period 10.000 [get_nets { clk_a }]
create_clock -period 13.333 [get_nets { clk_b }]
