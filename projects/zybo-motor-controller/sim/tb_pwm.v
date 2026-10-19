`timescale 1ns/1ps
module tb_pwm #(parameter integer PERIOD=1000);
    reg clk=0, reset=1, enable=0;
    reg [9:0] duty=0;
    wire out;
    integer d,k,total;
    always #5 clk=~clk;
    pwm #(.PERIOD(PERIOD)) dut (.clk(clk),.reset(reset),.enable(enable),.duty_permille(duty),.out(out));
    task frame;
        begin
            total=0;
            for(k=0;k<PERIOD;k=k+1) begin @(posedge clk); #1; if(out) total=total+1; end
        end
    endtask
    initial begin
        repeat(3) @(negedge clk); reset=0;
        for(d=0;d<=1000;d=d+1) begin
            enable=0; duty=d; @(negedge clk); enable=1;
            frame;
            if(total!=d*PERIOD/1000) $fatal(1,"PWM %0d count got %0d",d,total);
            @(negedge clk);
        end
        enable=0; duty=800; @(negedge clk); enable=1;
        repeat(100) @(negedge clk);
        duty=0;
        if(!out) $fatal(1,"Duty changed inside frame");
        enable=0; #1;
        if(out) $fatal(1,"Disable did not force output LOW");
        $display("PASS pwm: all 1001 duties, period %0d, frame latch, immediate inhibit",PERIOD); $finish;
    end
endmodule
