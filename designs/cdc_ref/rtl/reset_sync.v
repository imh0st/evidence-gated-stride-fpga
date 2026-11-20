`timescale 1ns / 1ps
// Reset synchronizer: asynchronous assertion, synchronous de-assertion.
module reset_sync (
    input  wire clk,
    input  wire arst_n,     // asynchronous, active low
    output wire rst_n
);
    reg [1:0] sync;

    always @(posedge clk or negedge arst_n) begin
        if (!arst_n) sync <= 2'b00;
        else         sync <= {sync[0], 1'b1};
    end

    assign rst_n = sync[1];
endmodule
