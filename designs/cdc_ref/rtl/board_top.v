`timescale 1ns / 1ps
// Board top shared by all three boards. Each board supplies its own clk_gen
// (a wrapper around the vendor PLL IP) and pin constraints.
module board_top (
    input  wire       clk,
    output wire [3:0] led
);
    wire clk_a, clk_b, locked;

    clk_gen u_clk (
        .clk_in(clk),
        .clk_a(clk_a),      // 100 MHz
        .clk_b(clk_b),      // 75 MHz
        .locked(locked)
    );

    cdc_ref_core u_core (
        .clk_a(clk_a),
        .clk_b(clk_b),
        .locked(locked),
        .led(led)
    );
endmodule
