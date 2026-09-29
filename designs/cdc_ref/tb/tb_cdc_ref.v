`timescale 1ps / 1ps
// Self-checking testbench for cdc_ref_core. Runs the producer/checker pair with
// the write clock faster than the read clock and the reverse, and fails if the
// checker sees an out-of-sequence byte or too few words arrive.
module tb_cdc_ref;
    localparam integer RUN_US    = 200;
    // Throughput is bounded by the slower clock (~75 words/us); require 90 % of it.
    localparam integer MIN_WORDS = RUN_US * 75 * 9 / 10;

    reg clk_fast = 0, clk_slow = 0, locked = 0;
    always #5000 clk_fast = ~clk_fast;      // 100 MHz
    always #6667 clk_slow = ~clk_slow;      // ~75 MHz

    wire [3:0] led_fw, led_sw;

    // Case 1: fast writer, slow reader (FIFO runs full)
    cdc_ref_core dut_fw (.clk_a(clk_fast), .clk_b(clk_slow), .locked(locked), .led(led_fw));
    // Case 2: slow writer, fast reader (FIFO runs empty)
    cdc_ref_core dut_sw (.clk_a(clk_slow), .clk_b(clk_fast), .locked(locked), .led(led_sw));

    initial begin
        #100_000 locked = 1;
        #(RUN_US * 1_000_000);
        $display("case fast-write: words=%0d error=%0b", dut_fw.words, dut_fw.error);
        $display("case slow-write: words=%0d error=%0b", dut_sw.words, dut_sw.error);
        if (!dut_fw.error && !dut_sw.error && dut_fw.words >= MIN_WORDS && dut_sw.words >= MIN_WORDS)
            $display("PASS");
        else
            $display("FAIL");
        $finish;
    end
endmodule
