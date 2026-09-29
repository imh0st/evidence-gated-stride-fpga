# Mark the two-flop synchronizers (FIFO pointers and reset) so that synthesis
# keeps them as flip-flops placed close together (AMD UG903, ASYNC_REG).
set_property ASYNC_REG TRUE [get_cells -hier -regexp {.*/(wq[12]_rptr|rq[12]_wptr|sync)_reg.*}]
