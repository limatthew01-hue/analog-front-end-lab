`timescale 1ns/1ps
module motor_top #(
    parameter integer CLK_HZ = 125000000,
    parameter integer BAUD = 115200,
    parameter integer PWM_HZ = 20000,
    parameter integer CPR_MILLI = 358331,
    parameter integer ENCODER_INVERT = 0
)(
    input wire sysclk, btn_reset, arm_switch,
    input wire encoder_a, encoder_b, driver_fault_n, uart_rx_pin,
    output wire motor_in1, motor_in2, uart_tx_pin,
    output wire [3:0] led);
    // Power-on hold, then synchronous release; no derived clock domains.
    reg [7:0] por = 0;
    (* ASYNC_REG = "TRUE" *) reg [2:0] io_meta = 0, io_sync = 0;
    always @(posedge sysclk) begin
        if (por != 255) por <= por+1;
        io_meta <= {btn_reset,arm_switch,driver_fault_n};
        io_sync <= io_meta;
    end
    wire reset = por != 255 || io_sync[2];
    wire cmd_valid, cmd_enable, cmd_clear, active, link_alive, requested_enable, tick;
    wire [15:0] cmd_target, target;
    wire signed [15:0] rpm;
    wire [9:0] duty;
    wire [7:0] faults, invalid_count;
    wire [7:0] status = {4'b0,requested_enable,link_alive,io_sync[1],active};
    motor_core #(.CLK_HZ(CLK_HZ),.PWM_HZ(PWM_HZ),.CPR_MILLI(CPR_MILLI),
                 .ENCODER_INVERT(ENCODER_INVERT)) core (
        .clk(sysclk),.reset(reset),.arm(io_sync[1]),.driver_fault_n(io_sync[0]),
        .encoder_a(encoder_a),.encoder_b(encoder_b),.cmd_valid(cmd_valid),
        .cmd_enable(cmd_enable),.cmd_clear(cmd_clear),.cmd_target(cmd_target),
        .pwm_out(motor_in1),.active(active),.link_alive(link_alive),.control_tick(tick),
        .duty_permille(duty),.measured_rpm_x10(rpm),.target_rpm(target),
        .requested_enable(requested_enable),.faults(faults),.invalid_count(invalid_count));
    assign motor_in2 = 0; // One direction, PWM/coast (never reverse or brake).
    serial_link #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) serial (
        .clk(sysclk),.reset(reset),.rx(uart_rx_pin),.tx(uart_tx_pin),
        .cmd_valid(cmd_valid),.cmd_enable(cmd_enable),.cmd_clear(cmd_clear),.cmd_target(cmd_target),
        .rpm_x10(rpm),.target_rpm(target),.duty(duty),.status(status),
        .faults(faults),.invalid_count(invalid_count));
    assign led = {requested_enable,link_alive,|faults,active};
endmodule
