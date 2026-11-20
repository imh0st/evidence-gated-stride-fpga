`timescale 1ns / 1ps
// Zybo Z7-20, open flow (openXC7): the PLL is instantiated as a primitive because
// the Clocking Wizard IP exists only in Vivado. 125 MHz in, VCO 1200 MHz
// (DIVCLK 5, MULT 48), outputs /12 = 100 MHz and /16 = 75 MHz.
module clk_gen (
    input  wire clk_in,
    output wire clk_a,
    output wire clk_b,
    output wire locked
);
    wire fb, a_unbuf, b_unbuf;

    PLLE2_BASE #(
        .CLKIN1_PERIOD (8.000),
        .DIVCLK_DIVIDE (5),
        .CLKFBOUT_MULT (48),
        .CLKOUT0_DIVIDE(12),
        .CLKOUT1_DIVIDE(16)
    ) u_pll (
        .CLKIN1  (clk_in),
        .CLKFBIN (fb),
        .CLKFBOUT(fb),
        .CLKOUT0 (a_unbuf),
        .CLKOUT1 (b_unbuf),
        .CLKOUT2 (),
        .CLKOUT3 (),
        .CLKOUT4 (),
        .CLKOUT5 (),
        .LOCKED  (locked),
        .PWRDWN  (1'b0),
        .RST     (1'b0)
    );

    BUFG u_bufg_a (.I(a_unbuf), .O(clk_a));
    BUFG u_bufg_b (.I(b_unbuf), .O(clk_b));
endmodule
