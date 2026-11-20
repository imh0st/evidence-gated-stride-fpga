`timescale 1ns / 1ps
// Dual-clock FIFO with Gray-coded pointers and two-flop pointer synchronizers,
// following Cummings, "Simulation and Synthesis Techniques for Asynchronous FIFO
// Design", SNUG 2002 (style #1: full/empty from Gray pointer comparison).
//
// The only signals that cross clock domains are the Gray-coded pointers
// (wptr_gray -> rq1_wptr, rptr_gray -> wq1_rptr) and the memory read path.
// Their timing is bounded by the board timing constraints (set_max_delay).
module async_fifo #(
    parameter DSIZE = 8,
    parameter ASIZE = 4
) (
    input  wire             wclk,
    input  wire             wrst_n,
    input  wire             winc,
    input  wire [DSIZE-1:0] wdata,
    output reg              wfull,

    input  wire             rclk,
    input  wire             rrst_n,
    input  wire             rinc,
    output wire [DSIZE-1:0] rdata,
    output reg              rempty
);
    reg [DSIZE-1:0] mem [0:(1<<ASIZE)-1];
    reg [ASIZE:0]   wptr_gray, rptr_gray;       // the only pointers that cross domains

    // Write domain
    reg  [ASIZE:0] wbin;
    reg  [ASIZE:0] wq1_rptr, wq2_rptr;          // read pointer synchronized into wclk
    wire [ASIZE:0] wbin_next  = wbin + (winc & ~wfull);
    wire [ASIZE:0] wgray_next = (wbin_next >> 1) ^ wbin_next;
    wire           wfull_next = (wgray_next == {~wq2_rptr[ASIZE:ASIZE-1], wq2_rptr[ASIZE-2:0]});

    always @(posedge wclk) begin
        if (winc & ~wfull)
            mem[wbin[ASIZE-1:0]] <= wdata;
    end

    always @(posedge wclk or negedge wrst_n) begin
        if (!wrst_n) begin
            wbin      <= 0;
            wptr_gray <= 0;
            wfull     <= 1'b0;
            wq1_rptr  <= 0;
            wq2_rptr  <= 0;
        end else begin
            wbin      <= wbin_next;
            wptr_gray <= wgray_next;
            wfull     <= wfull_next;
            wq1_rptr  <= rptr_gray;
            wq2_rptr  <= wq1_rptr;
        end
    end

    // Read domain
    reg  [ASIZE:0] rbin;
    reg  [ASIZE:0] rq1_wptr, rq2_wptr;          // write pointer synchronized into rclk
    wire [ASIZE:0] rbin_next   = rbin + (rinc & ~rempty);
    wire [ASIZE:0] rgray_next  = (rbin_next >> 1) ^ rbin_next;
    wire           rempty_next = (rgray_next == rq2_wptr);

    assign rdata = mem[rbin[ASIZE-1:0]];

    always @(posedge rclk or negedge rrst_n) begin
        if (!rrst_n) begin
            rbin      <= 0;
            rptr_gray <= 0;
            rempty    <= 1'b1;
            rq1_wptr  <= 0;
            rq2_wptr  <= 0;
        end else begin
            rbin      <= rbin_next;
            rptr_gray <= rgray_next;
            rempty    <= rempty_next;
            rq1_wptr  <= wptr_gray;
            rq2_wptr  <= rq1_wptr;
        end
    end
endmodule
