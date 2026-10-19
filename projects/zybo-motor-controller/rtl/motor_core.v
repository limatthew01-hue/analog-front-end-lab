`timescale 1ns/1ps
module motor_core #(
    parameter integer CLK_HZ = 125000000,
    parameter integer CONTROL_HZ = 50,
    parameter integer PWM_HZ = 20000,
    parameter integer CPR_MILLI = 358331,
    parameter integer ENCODER_INVERT = 0,
    parameter integer WATCHDOG_MS = 500,
    parameter integer STALL_MS = 1000,
    parameter integer KP_Q8 = 256,
    parameter integer KI_STEP_Q8 = 24
)(input wire clk, reset,
  // arm and driver_fault_n must already be synchronized to clk.
  input wire arm, driver_fault_n, encoder_a, encoder_b,
  input wire cmd_valid, cmd_enable, cmd_clear,
  input wire [15:0] cmd_target,
  output wire pwm_out, active, link_alive, control_tick,
  output wire [9:0] duty_permille,
  output reg signed [15:0] measured_rpm_x10 = 0,
  output reg [15:0] target_rpm = 0,
  output reg requested_enable = 0,
  output reg [7:0] faults = 0,
  output wire [7:0] invalid_count);
    localparam integer CONTROL_DIV = CLK_HZ / CONTROL_HZ;
    localparam integer WATCHDOG_CYCLES = (CLK_HZ / 1000) * WATCHDOG_MS;
    localparam integer STALL_CYCLES = (CLK_HZ / 1000) * STALL_MS;
    reg [31:0] control_count = 0, watchdog_count = 0, stall_count = 0;
    reg has_command = 0;
    reg [1:0] reverse_count = 0;
    wire signed [1:0] step;
    wire illegal;
    reg signed [31:0] window_count = 0;
    wire signed [63:0] window_total = $signed(window_count) + $signed(step);
    wire signed [63:0] raw_speed = (window_total * 64'sd600000 * CONTROL_HZ) / CPR_MILLI;
    wire signed [63:0] filtered_speed = measured_rpm_x10 + (raw_speed - measured_rpm_x10) / 4;
    wire accepted = cmd_valid && cmd_target <= 600;
    wire [7:0] new_faults =
        (!driver_fault_n ? 8'h01 : 0) |
        (arm && requested_enable && target_rpm != 0 && has_command &&
         !link_alive ? 8'h02 : 0) |
        (active && stall_count >= STALL_CYCLES-1 ? 8'h04 : 0) |
        (active && illegal ? 8'h08 : 0) |
        (active && step < 0 && reverse_count == 2 ? 8'h10 : 0);

    assign link_alive = has_command && watchdog_count < WATCHDOG_CYCLES;
    assign active = !reset && arm && driver_fault_n && link_alive &&
                    requested_enable && target_rpm != 0 && faults == 0;
    assign control_tick = control_count == CONTROL_DIV-1;
    quadrature #(.INVERT(ENCODER_INVERT)) encoder (
        .clk(clk),.reset(reset),.a(encoder_a),.b(encoder_b),
        .step(step),.illegal(illegal),.invalid_count(invalid_count));
    pi_controller #(.KP_Q8(KP_Q8),.KI_STEP_Q8(KI_STEP_Q8)) controller (
        .clk(clk),.reset(reset),.tick(control_tick),.enable(active),
        .target_rpm(target_rpm),.measured_rpm_x10(measured_rpm_x10),
        .duty_permille(duty_permille));
    pwm #(.PERIOD(CLK_HZ/PWM_HZ)) drive (
        .clk(clk),.reset(reset),.enable(active),
        .duty_permille(duty_permille),.out(pwm_out));

    always @(posedge clk) begin
        if (reset) begin
            target_rpm <= 0; requested_enable <= 0; faults <= 0;
            watchdog_count <= 0; has_command <= 0;
            control_count <= 0; window_count <= 0; measured_rpm_x10 <= 0;
            stall_count <= 0; reverse_count <= 0;
        end else begin
            if (accepted) begin
                target_rpm <= cmd_target;
                requested_enable <= cmd_enable;
                watchdog_count <= 0;
                has_command <= 1;
            end else if (watchdog_count < WATCHDOG_CYCLES)
                watchdog_count <= watchdog_count + 1;

            // Clear faults only with the physical arm switch OFF and a stop frame.
            if (accepted && cmd_clear && !cmd_enable && cmd_target == 0 &&
                !arm && driver_fault_n) faults <= 0;
            else faults <= faults | new_faults;

            if (!active || duty_permille < 250 || step != 0) stall_count <= 0;
            else if (stall_count < STALL_CYCLES) stall_count <= stall_count + 1;
            if (!active || step > 0) reverse_count <= 0;
            else if (step < 0 && reverse_count < 3) reverse_count <= reverse_count + 1;

            if (control_tick) begin
                control_count <= 0;
                window_count <= 0;
                if (filtered_speed > 32767) measured_rpm_x10 <= 32767;
                else if (filtered_speed < -32768) measured_rpm_x10 <= -32768;
                else measured_rpm_x10 <= filtered_speed[15:0];
            end else begin
                control_count <= control_count + 1;
                window_count <= window_total[31:0];
            end
        end
    end
endmodule
