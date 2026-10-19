`timescale 1ns/1ps
module uart_rx #(parameter integer CLKS_PER_BIT = 1085)(
    input wire clk, reset, rx,
    output reg [7:0] data = 0, output reg valid = 0);
    (* ASYNC_REG = "TRUE" *) reg rx_meta = 1, rx_sync = 1;
    reg [1:0] state = 0;
    reg [31:0] count = 0;
    reg [2:0] bit_index = 0;
    reg [7:0] shift = 0;
    always @(posedge clk) begin
        rx_meta <= rx; rx_sync <= rx_meta; valid <= 0;
        if (reset) begin state <= 0; count <= 0; end
        else case (state)
            0: if (!rx_sync) begin state <= 1; count <= CLKS_PER_BIT/2-1; end
            1: if (count == 0) begin
                if (!rx_sync) begin state <= 2; bit_index <= 0; count <= CLKS_PER_BIT-1; end
                else state <= 0;
            end else count <= count-1;
            2: if (count == 0) begin
                shift[bit_index] <= rx_sync; count <= CLKS_PER_BIT-1;
                if (bit_index == 7) state <= 3; else bit_index <= bit_index+1;
            end else count <= count-1;
            3: if (count == 0) begin
                if (rx_sync) begin data <= shift; valid <= 1; end
                state <= 0;
            end else count <= count-1;
        endcase
    end
endmodule

module uart_tx #(parameter integer CLKS_PER_BIT = 1085)(
    input wire clk, reset, start, input wire [7:0] data,
    output wire tx, output wire busy);
    reg [9:0] frame = 10'h3ff;
    reg [3:0] bits_left = 0;
    reg [31:0] count = 0;
    assign tx = bits_left == 0 ? 1'b1 : frame[0];
    assign busy = bits_left != 0;
    always @(posedge clk) begin
        if (reset) begin bits_left <= 0; count <= 0; frame <= 10'h3ff; end
        else if (bits_left == 0) begin
            if (start) begin frame <= {1'b1,data,1'b0}; bits_left <= 10; count <= CLKS_PER_BIT-1; end
        end else if (count == 0) begin
            frame <= {1'b1,frame[9:1]}; bits_left <= bits_left-1; count <= CLKS_PER_BIT-1;
        end else count <= count-1;
    end
endmodule
