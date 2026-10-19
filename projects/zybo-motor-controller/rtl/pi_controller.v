`timescale 1ns/1ps
// Error is in 0.1 RPM. Gains use Q8 duty-per-RPM units.
// KI_STEP_Q8 includes Ts; retune if CONTROL_HZ changes.
module pi_controller #(
    parameter integer KP_Q8 = 256,
    parameter integer KI_STEP_Q8 = 24,
    parameter integer MAX_DUTY = 900
)(input wire clk, reset, tick, enable,
  input wire [15:0] target_rpm,
  input wire signed [15:0] measured_rpm_x10,
  output reg [9:0] duty_permille = 0);
    reg signed [63:0] integral = 0;
    wire signed [63:0] error_x10 = $signed({1'b0,target_rpm}) * 64'sd10 - measured_rpm_x10;
    wire signed [63:0] candidate_i = integral + error_x10 * KI_STEP_Q8;
    wire signed [63:0] candidate_u = error_x10 * KP_Q8 + candidate_i;
    wire hold_integral = (candidate_u > MAX_DUTY * 2560 && error_x10 > 0) ||
                         (candidate_u < 0 && error_x10 < 0);
    wire signed [63:0] chosen_i = hold_integral ? integral : candidate_i;
    wire signed [63:0] output_q = candidate_u / 2560;
    always @(posedge clk) begin
        if (reset || !enable || target_rpm == 0) begin
            integral <= 0;
            duty_permille <= 0;
        end else if (tick) begin
            integral <= chosen_i;
            if (output_q < 0) duty_permille <= 0;
            else if (output_q > MAX_DUTY) duty_permille <= MAX_DUTY;
            else duty_permille <= output_q[9:0];
        end
    end
endmodule
