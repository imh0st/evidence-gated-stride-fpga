`timescale 1ns / 1ps
// PolarFire SoC Discovery Kit: Microchip PF_CCC IP, 50 MHz in -> 100 MHz / 75 MHz.
// The 50 MHz reference enters through a CLKBUF on the dedicated CCC input, as in
// Microchip's Discovery Kit reference design. PF_CCC_C0 is generated from
// boards/disco/pf_ccc.tcl by flows/libero/build.tcl.
module clk_gen (
    input  wire clk_in,
    output wire clk_a,
    output wire clk_b,
    output wire locked
);
    wire ref_clk;

    CLKBUF u_clkbuf (
        .PAD(clk_in),
        .Y  (ref_clk)
    );

    PF_CCC_C0 u_ccc (
        .REF_CLK_0    (ref_clk),
        .OUT0_FABCLK_0(clk_a),
        .OUT1_FABCLK_0(clk_b),
        .PLL_LOCK_0   (locked)
    );
endmodule
