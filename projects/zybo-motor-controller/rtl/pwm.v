`timescale 1ns/1ps
// Frame-latched duty; disabling bypasses the latch and immediately forces coast.
module pwm #(
    parameter integer PERIOD = 6250
)(input wire clk, reset, enable,
  input wire [9:0] duty_permille,
  output wire out);
    reg [31:0] phase = 0;
    reg [31:0] high_cycles = 0;
    wire [31:0] limited = duty_permille > 1000 ? 1000 : duty_permille;
    always @(posedge clk) begin
        if (reset || !enable) begin
            phase <= PERIOD-1;
            high_cycles <= 0;
        end else if (phase == PERIOD-1) begin
            phase <= 0;
            high_cycles <= (limited * PERIOD) / 1000;
        end else phase <= phase + 1;
    end
    assign out = !reset && enable && (phase < high_cycles);
endmodule
