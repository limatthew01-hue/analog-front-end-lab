`timescale 1ns/1ps
// CRC-8/SMBUS: polynomial 0x07, init 0, non-reflected, xorout 0.
module serial_link #(
    parameter integer CLK_HZ = 125000000,
    parameter integer BAUD = 115200,
    parameter integer TELEMETRY_HZ = 20
)(input wire clk, reset, rx,
  output wire tx,
  output reg cmd_valid = 0, cmd_enable = 0, cmd_clear = 0,
  output reg [15:0] cmd_target = 0,
  input wire signed [15:0] rpm_x10,
  input wire [15:0] target_rpm,
  input wire [9:0] duty,
  input wire [7:0] status, faults, invalid_count);
    function [7:0] crc_byte;
        input [7:0] crc, value;
        reg [7:0] c;
        integer i;
        begin
            c = crc ^ value;
            for (i=0;i<8;i=i+1) c = c[7] ? (c << 1) ^ 8'h07 : c << 1;
            crc_byte = c;
        end
    endfunction
    wire [7:0] rx_byte;
    wire rx_valid;
    reg [2:0] rx_index = 0;
    reg [7:0] rx_crc = 0, low_target = 0, high_target = 0, flags = 0;
    reg [31:0] rx_idle = 0;
    uart_rx #(.CLKS_PER_BIT(CLK_HZ/BAUD)) receiver (
        .clk(clk),.reset(reset),.rx(rx),.data(rx_byte),.valid(rx_valid));
    always @(posedge clk) begin
        cmd_valid <= 0;
        if (reset) begin rx_index <= 0; rx_idle <= 0; cmd_target <= 0; cmd_enable <= 0; cmd_clear <= 0; end
        else if (rx_valid) begin
            rx_idle <= 0;
            if (rx_index == 0) begin
                if (rx_byte == 8'ha5) begin rx_crc <= crc_byte(0,rx_byte); rx_index <= 1; end
            end else if (rx_index < 5) begin
                rx_crc <= crc_byte(rx_crc,rx_byte);
                if (rx_index == 2) low_target <= rx_byte;
                if (rx_index == 3) high_target <= rx_byte;
                if (rx_index == 4) flags <= rx_byte;
                rx_index <= rx_index+1;
            end else begin
                rx_index <= 0;
                if (rx_byte == rx_crc && flags <= 3 && {high_target,low_target} <= 600 &&
                    !(flags[1] && (flags[0] || {high_target,low_target} != 0))) begin
                    cmd_target <= {high_target,low_target};
                    cmd_enable <= flags[0]; cmd_clear <= flags[1]; cmd_valid <= 1;
                end
            end
        end else if (rx_index != 0) begin
            if (rx_idle >= CLK_HZ/50) begin rx_index <= 0; rx_idle <= 0; end
            else rx_idle <= rx_idle+1;
        end
    end

    reg [31:0] telemetry_count = 0;
    reg [7:0] packet [0:11];
    reg [7:0] packet_seq = 0, checksum;
    reg [3:0] tx_index = 0;
    reg [1:0] tx_state = 0;
    reg sending = 0, tx_start = 0;
    reg [7:0] tx_data = 0;
    wire tx_busy;
    integer j;
    uart_tx #(.CLKS_PER_BIT(CLK_HZ/BAUD)) transmitter (
        .clk(clk),.reset(reset),.start(tx_start),.data(tx_data),.tx(tx),.busy(tx_busy));
    always @(posedge clk) begin
        tx_start <= 0;
        if (reset) begin
            telemetry_count <= 0; sending <= 0; tx_state <= 0; packet_seq <= 0; tx_index <= 0;
        end else begin
            if (telemetry_count == CLK_HZ/TELEMETRY_HZ-1) begin
                telemetry_count <= 0;
                if (!sending) begin
                    packet[0] = 8'h5a; packet[1] = packet_seq;
                    packet[2] = rpm_x10[7:0]; packet[3] = rpm_x10[15:8];
                    packet[4] = target_rpm[7:0]; packet[5] = target_rpm[15:8];
                    packet[6] = duty[7:0]; packet[7] = {6'b0,duty[9:8]};
                    packet[8] = status; packet[9] = faults; packet[10] = invalid_count;
                    checksum = 0;
                    for (j=0;j<11;j=j+1) checksum = crc_byte(checksum,packet[j]);
                    packet[11] = checksum;
                    packet_seq <= packet_seq+1; sending <= 1; tx_index <= 0; tx_state <= 0;
                end
            end else telemetry_count <= telemetry_count+1;
            if (sending) case (tx_state)
                0: if (!tx_busy) begin tx_data <= packet[tx_index]; tx_start <= 1; tx_state <= 1; end
                1: if (tx_busy) tx_state <= 2;
                2: if (!tx_busy) begin
                    if (tx_index == 11) sending <= 0;
                    else begin tx_index <= tx_index+1; tx_state <= 0; end
                end
            endcase
        end
    end
endmodule
