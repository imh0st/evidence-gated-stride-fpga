# Clock-domain crossing constraints for the async FIFO (approved).
# Bound every path between the two PLL clocks by the source clock period, so
# that Gray-coded pointer bits arrive within one cycle of each other. The hold
# check is relaxed by one destination period: the two-flop synchronizer, not a
# clock relationship, makes the capture safe (the counterpart of Vivado's
# -datapath_only, which drops the hold check on these paths).
set clk_a [get_clocks {u_clk|u_pll|auto_generated|pll1|clk[0]}]
set clk_b [get_clocks {u_clk|u_pll|auto_generated|pll1|clk[1]}]
set_max_delay -from $clk_a -to $clk_b 10.000
set_max_delay -from $clk_b -to $clk_a 13.333
set_min_delay -from $clk_a -to $clk_b -13.333
set_min_delay -from $clk_b -to $clk_a -10.000
