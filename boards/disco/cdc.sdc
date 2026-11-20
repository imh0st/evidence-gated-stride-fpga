# Clock-domain crossing constraints for the async FIFO (approved).
# Bound every path between the two CCC clocks by the source clock period, so
# that Gray-coded pointer bits arrive within one cycle of each other. The hold
# check is relaxed by one destination period: the two-flop synchronizer, not a
# clock relationship, makes the capture safe (the counterpart of Vivado's
# -datapath_only, which drops the hold check on these paths).
# Clock names are those created by derive_constraints_sdc for PF_CCC_C0.
set_max_delay 10.000 -from [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT0}] -to [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT1}]
set_max_delay 13.333 -from [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT1}] -to [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT0}]
set_min_delay -13.333 -from [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT0}] -to [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT1}]
set_min_delay -10.000 -from [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT1}] -to [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT0}]
