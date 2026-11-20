# Clock-domain crossing constraints for the async FIFO (approved).
# AMD UG949 "Defining Clock Groups and CDC Constraints" / UG903: bound Gray-coded
# CDC paths with set_max_delay -datapath_only (source clock period) and limit the
# skew between pointer bits with set_bus_skew.
# Used in implementation only (the clock wizard is a black box during synthesis).
set clk_a [get_clocks -of_objects [get_pins u_clk/u_pll/inst/mmcm_adv_inst/CLKOUT0]]
set clk_b [get_clocks -of_objects [get_pins u_clk/u_pll/inst/mmcm_adv_inst/CLKOUT1]]
set_max_delay -datapath_only -from $clk_a -to $clk_b [get_property PERIOD $clk_a]
set_max_delay -datapath_only -from $clk_b -to $clk_a [get_property PERIOD $clk_b]

# Pointer buses: every register bit that feeds the first synchronizer stage
# (synthesis may merge the Gray MSB with the binary MSB, so trace the fan-in).
set wptr_src [all_fanin -startpoints_only -flat [get_pins u_core/u_fifo/rq1_wptr_reg*/D]]
set rptr_src [all_fanin -startpoints_only -flat [get_pins u_core/u_fifo/wq1_rptr_reg*/D]]
set_bus_skew -from $wptr_src -to [get_pins u_core/u_fifo/rq1_wptr_reg*/D] [get_property PERIOD $clk_b]
set_bus_skew -from $rptr_src -to [get_pins u_core/u_fifo/wq1_rptr_reg*/D] [get_property PERIOD $clk_a]

# Signoff waivers.
# The FIFO memory is read in clk_b only at addresses whose write has been
# published through the synchronized Gray pointer (Cummings 2002), so the
# memory read path needs no synchronizer.
set mem_clk [get_pins -hier -filter {NAME =~ u_core/u_fifo/mem_reg*/CLK}]
create_waiver -type CDC -id {CDC-1} -from $mem_clk -to [get_pins u_core/error_reg/CE] \
    -user cdc_ref -description {FIFO memory read guarded by Gray-pointer handshake}
create_waiver -type CDC -id {CDC-15} -from $mem_clk -to [get_pins u_core/error_reg/D] \
    -user cdc_ref -description {FIFO memory read guarded by Gray-pointer handshake}
# The pointer buses are Gray coded and their bit skew is bounded above.
create_waiver -type CDC -id {CDC-6} -from $wptr_src -to [get_pins u_core/u_fifo/rq1_wptr_reg*/D] \
    -user cdc_ref -description {Gray-coded write pointer; bit skew bounded by set_bus_skew}
create_waiver -type CDC -id {CDC-6} -from $rptr_src -to [get_pins u_core/u_fifo/wq1_rptr_reg*/D] \
    -user cdc_ref -description {Gray-coded read pointer; bit skew bounded by set_bus_skew}
