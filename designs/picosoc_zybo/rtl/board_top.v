`timescale 1ns / 1ps
// PicoSoC (upstream picosoc.v, spimemio.v, simpleuart.v, picorv32.v, unmodified) on the
// Digilent Zybo Z7-20. Port of upstream picosoc/hx8kdemo.v: the iCE40 SB_IO flash buffers
// become tristate assignments, the clock comes from the 125 MHz board input through the
// PLL of clk_gen.v (50 MHz output), the GPIO drives the four LEDs, and the
// UART and the SPI flash interface are placed on Pmod JE.
module board_top (
    input  wire       clk,
    output wire [3:0] led,
    output wire       ser_tx,
    input  wire       ser_rx,
    output wire       flash_csb,
    output wire       flash_clk,
    inout  wire       flash_io0,
    inout  wire       flash_io1,
    inout  wire       flash_io2,
    inout  wire       flash_io3
);
    wire clk_a, clk_b, locked;
    clk_gen u_clk (.clk_in(clk), .clk_a(clk_a), .clk_b(clk_b), .locked(locked));
    wire sclk = clk_b;

    reg [5:0] reset_cnt = 0;
    wire resetn = &reset_cnt;
    always @(posedge sclk) reset_cnt <= reset_cnt + {5'd0, !resetn & locked};

    wire flash_io0_oe, flash_io0_do, flash_io0_di;
    wire flash_io1_oe, flash_io1_do, flash_io1_di;
    wire flash_io2_oe, flash_io2_do, flash_io2_di;
    wire flash_io3_oe, flash_io3_do, flash_io3_di;
    assign flash_io0 = flash_io0_oe ? flash_io0_do : 1'bz;
    assign flash_io1 = flash_io1_oe ? flash_io1_do : 1'bz;
    assign flash_io2 = flash_io2_oe ? flash_io2_do : 1'bz;
    assign flash_io3 = flash_io3_oe ? flash_io3_do : 1'bz;
    assign flash_io0_di = flash_io0;
    assign flash_io1_di = flash_io1;
    assign flash_io2_di = flash_io2;
    assign flash_io3_di = flash_io3;

    wire        iomem_valid;
    reg         iomem_ready;
    wire [3:0]  iomem_wstrb;
    wire [31:0] iomem_addr;
    wire [31:0] iomem_wdata;
    reg  [31:0] iomem_rdata;
    reg  [31:0] gpio;
    assign led = gpio[3:0];

    always @(posedge sclk) begin
        if (!resetn) begin
            gpio <= 0;
        end else begin
            iomem_ready <= 0;
            if (iomem_valid && !iomem_ready && iomem_addr[31:24] == 8'h03) begin
                iomem_ready <= 1;
                iomem_rdata <= gpio;
                if (iomem_wstrb[0]) gpio[ 7: 0] <= iomem_wdata[ 7: 0];
                if (iomem_wstrb[1]) gpio[15: 8] <= iomem_wdata[15: 8];
                if (iomem_wstrb[2]) gpio[23:16] <= iomem_wdata[23:16];
                if (iomem_wstrb[3]) gpio[31:24] <= iomem_wdata[31:24];
            end
        end
    end

    picosoc soc (
        .clk(sclk), .resetn(resetn), .ser_tx(ser_tx), .ser_rx(ser_rx),
        .flash_csb(flash_csb), .flash_clk(flash_clk),
        .flash_io0_oe(flash_io0_oe), .flash_io1_oe(flash_io1_oe), .flash_io2_oe(flash_io2_oe), .flash_io3_oe(flash_io3_oe),
        .flash_io0_do(flash_io0_do), .flash_io1_do(flash_io1_do), .flash_io2_do(flash_io2_do), .flash_io3_do(flash_io3_do),
        .flash_io0_di(flash_io0_di), .flash_io1_di(flash_io1_di), .flash_io2_di(flash_io2_di), .flash_io3_di(flash_io3_di),
        .irq_5(1'b0), .irq_6(1'b0), .irq_7(1'b0),
        .iomem_valid(iomem_valid), .iomem_ready(iomem_ready), .iomem_wstrb(iomem_wstrb),
        .iomem_addr(iomem_addr), .iomem_wdata(iomem_wdata), .iomem_rdata(iomem_rdata)
    );
endmodule
