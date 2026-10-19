`timescale 1ns/1ps
module tb_core;
    reg clk=0,reset=1,arm=0,fault_n=1,a=0,b=0;
    reg valid=0,en=0,clear=0;
    reg [15:0] target=0;
    wire pwm_out,active,alive,tick,requested;
    wire [9:0] duty;
    wire signed [15:0] rpm;
    wire [15:0] requested_target;
    wire [7:0] faults,invalid;
    integer i;
    always #5 clk=~clk;
    always @(negedge clk) if(!reset &&
        ((^duty === 1'bx) || (^rpm === 1'bx) || (pwm_out === 1'bx)))
        $fatal(1,"Undefined controller output");
    motor_core #(.CLK_HZ(100000),.PWM_HZ(1000),.CPR_MILLI(600000),
        .WATCHDOG_MS(50),.STALL_MS(100)) dut (
        .clk(clk),.reset(reset),.arm(arm),.driver_fault_n(fault_n),.encoder_a(a),.encoder_b(b),
        .cmd_valid(valid),.cmd_enable(en),.cmd_clear(clear),.cmd_target(target),
        .pwm_out(pwm_out),.active(active),.link_alive(alive),.control_tick(tick),
        .duty_permille(duty),.measured_rpm_x10(rpm),.target_rpm(requested_target),
        .requested_enable(requested),.faults(faults),.invalid_count(invalid));
    task send;
        input integer speed,run,clr;
        begin
            @(negedge clk); target=speed;en=run;clear=clr;valid=1;
            @(negedge clk); valid=0; clear=0;
        end
    endtask
    task restart;
        begin reset=1;arm=0;fault_n=1;a=0;b=0;valid=0;
            repeat(10) @(negedge clk); reset=0; repeat(10) @(negedge clk); end
    endtask
    task state;
        input [1:0] value;
        begin {a,b}=value; repeat(8) @(negedge clk); end
    endtask
    initial begin
        restart; send(300,1,0); repeat(2200) @(negedge clk);
        if(active || pwm_out) $fatal(1,"Unarmed command moved motor");
        arm=1; repeat(10) @(negedge clk);
        if(!active) $fatal(1,"Fresh armed command inactive");
        arm=0; #1; if(pwm_out) $fatal(1,"Disarm did not inhibit PWM");
        arm=1; fault_n=0; repeat(4) @(negedge clk);
        if(faults!=1 || active || pwm_out) $fatal(1,"Driver fault not latched");
        fault_n=1; send(0,0,1);
        if(faults!=1) $fatal(1,"Clear accepted while armed");
        arm=0; send(0,0,1);
        if(faults!=0 || active) $fatal(1,"Stopped clear failed");

        restart; arm=1; send(300,1,0);
        repeat(5100) @(negedge clk);
        if(!(faults&2) || active || pwm_out) $fatal(1,"Watchdog failed");
        send(300,1,0); if(active) $fatal(1,"Fault automatically restarted");

        restart; arm=1; send(300,1,0);
        for(i=0;i<20;i=i+1) begin send(300,1,0); repeat(1500) @(negedge clk); end
        if(!(faults&4) || active) $fatal(1,"Missing encoder motion did not stop motor");

        restart; arm=1; send(300,1,0); state(3);
        if(!(faults&8) || active) $fatal(1,"Illegal encoder transition failed");

        restart; arm=1; send(300,1,0); state(2);state(3);state(1);state(0);
        if(!(faults&16) || active) $fatal(1,"Reverse encoder motion not detected");

        restart; arm=1; send(300,1,0);
        // A valid but out-of-range direct command cannot refresh the watchdog.
        for(i=0;i<6;i=i+1) begin send(601,1,0); repeat(1000) @(negedge clk); end
        if(!(faults&2) || requested_target!=300) $fatal(1,"Invalid target refreshed command");
        $display("PASS core: arm, coast, driver latch, clear, watchdog, stall, encoder faults, bounds"); $finish;
    end
endmodule
