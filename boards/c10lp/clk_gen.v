`timescale 1ns / 1ps
// Cyclone 10 LP Evaluation Kit: Altera ALTPLL IP, 50 MHz in -> 100 MHz / 75 MHz.
// Parameters follow the ALTPLL IP user guide; this is the instantiation the
// IP parameter editor generates for a two-output normal-mode PLL.
module clk_gen (
    input  wire clk_in,
    output wire clk_a,
    output wire clk_b,
    output wire locked
);
    wire [4:0] clk;

    altpll #(
        .intended_device_family ("Cyclone 10 LP"),
        .lpm_type               ("altpll"),
        .operation_mode         ("NORMAL"),
        .pll_type               ("AUTO"),
        .bandwidth_type         ("AUTO"),
        .compensate_clock       ("CLK0"),
        .inclk0_input_frequency (20000),        // ps, 50 MHz
        .clk0_multiply_by       (2),            // 100 MHz
        .clk0_divide_by         (1),
        .clk0_duty_cycle        (50),
        .clk0_phase_shift       ("0"),
        .clk1_multiply_by       (3),            // 75 MHz
        .clk1_divide_by         (2),
        .clk1_duty_cycle        (50),
        .clk1_phase_shift       ("0"),
        .port_inclk0            ("PORT_USED"),
        .port_clk0              ("PORT_USED"),
        .port_clk1              ("PORT_USED"),
        .port_clk2              ("PORT_UNUSED"),
        .port_clk3              ("PORT_UNUSED"),
        .port_clk4              ("PORT_UNUSED"),
        .port_locked            ("PORT_USED"),
        .port_areset            ("PORT_UNUSED"),
        .self_reset_on_loss_lock("OFF"),
        .width_clock            (5)
    ) u_pll (
        .inclk ({1'b0, clk_in}),
        .clk   (clk),
        .locked(locked)
    );

    assign clk_a = clk[0];
    assign clk_b = clk[1];
endmodule
