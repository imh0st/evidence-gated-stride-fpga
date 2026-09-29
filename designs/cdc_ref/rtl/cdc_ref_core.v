`timescale 1ns / 1ps
// Reference design: a producer in clk_a streams an incrementing byte sequence
// through an asynchronous FIFO to a checker in clk_b.
//
// LEDs: [0] heartbeat (clk_b)  [1] clocks locked  [2] sequence error (sticky)
//       [3] data flowing (toggles every 2^HB_BITS words read)
module cdc_ref_core #(
    parameter HB_BITS = 24
) (
    input  wire       clk_a,
    input  wire       clk_b,
    input  wire       locked,
    output wire [3:0] led
);
    wire rst_a_n, rst_b_n;
    reset_sync u_rst_a (.clk(clk_a), .arst_n(locked), .rst_n(rst_a_n));
    reset_sync u_rst_b (.clk(clk_b), .arst_n(locked), .rst_n(rst_b_n));

    // Producer (clk_a)
    reg  [7:0] wdata;
    wire       wfull;
    wire       winc = ~wfull;

    always @(posedge clk_a or negedge rst_a_n) begin
        if (!rst_a_n)   wdata <= 8'd0;
        else if (winc)  wdata <= wdata + 8'd1;
    end

    // FIFO
    wire [7:0] rdata;
    wire       rempty;
    wire       rinc = ~rempty;

    async_fifo #(.DSIZE(8), .ASIZE(4)) u_fifo (
        .wclk(clk_a), .wrst_n(rst_a_n), .winc(winc), .wdata(wdata), .wfull(wfull),
        .rclk(clk_b), .rrst_n(rst_b_n), .rinc(rinc), .rdata(rdata), .rempty(rempty)
    );

    // Checker (clk_b)
    reg [7:0]         expected;
    reg               error;
    reg [HB_BITS-1:0] words, beat;

    always @(posedge clk_b or negedge rst_b_n) begin
        if (!rst_b_n) begin
            expected <= 8'd0;
            error    <= 1'b0;
            words    <= 0;
            beat     <= 0;
        end else begin
            beat <= beat + 1'b1;
            if (rinc) begin
                expected <= expected + 8'd1;
                words    <= words + 1'b1;
                if (rdata != expected) error <= 1'b1;
            end
        end
    end

    assign led = {words[HB_BITS-1], error, locked, beat[HB_BITS-1]};
endmodule
