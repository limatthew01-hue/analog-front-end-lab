`timescale 1ns/1ps
// End-to-end UART command -> synchronized arm -> PWM -> UART stop/fault clear.
module tb_top;
    reg clk=0,reset_button=0,arm=0,fault_n=1,rx=1;
    wire in1,in2,tx;
    wire [3:0] led;
    integer highs=0,i;
    always #5 clk=~clk;
    motor_top #(.CLK_HZ(160000),.BAUD(10000),.PWM_HZ(1000)) dut (
        .sysclk(clk),.btn_reset(reset_button),.arm_switch(arm),.encoder_a(1'b0),.encoder_b(1'b0),
        .driver_fault_n(fault_n),.uart_rx_pin(rx),.motor_in1(in1),.motor_in2(in2),.uart_tx_pin(tx),.led(led));
    function [7:0] crc;
        input [7:0] old,value;
        reg [7:0] result;integer k;
        begin result=old^value;
            for(k=0;k<8;k=k+1) result=result[7] ? (result<<1)^8'h07 : result<<1;
            crc=result;
        end
    endfunction
    task byte_out;
        input [7:0] value; integer k;
        begin rx=0;repeat(16) @(negedge clk);
            for(k=0;k<8;k=k+1) begin rx=value[k];repeat(16) @(negedge clk);end
            rx=1;repeat(16) @(negedge clk);
        end
    endtask
    task send;
        input [15:0] rpm; input [7:0] flags;reg [7:0] c;
        begin
            c=crc(crc(crc(crc(crc(0,8'ha5),0),rpm[7:0]),rpm[15:8]),flags);
            byte_out(8'ha5);byte_out(0);byte_out(rpm[7:0]);byte_out(rpm[15:8]);byte_out(flags);byte_out(c);
            repeat(8) @(negedge clk);
        end
    endtask
    initial begin
        repeat(300) @(negedge clk);
        send(100,1);repeat(4000) @(negedge clk);
        if(in1 || in2 || led[0]) $fatal(1,"Unarmed UART command drove outputs");
        arm=1;
        for(i=0;i<4000;i=i+1) begin @(negedge clk);if(in1) highs=highs+1;end
        if(highs==0 || in2 || !led[0]) $fatal(1,"Valid armed UART command produced no PWM");
        send(0,0);repeat(4) @(negedge clk);
        if(in1 || led[0]) $fatal(1,"UART stop failed");
        send(100,1);fault_n=0;repeat(10) @(negedge clk);
        if(in1 || !led[1]) $fatal(1,"Synchronized driver fault failed");
        fault_n=1;arm=0;repeat(10) @(negedge clk);send(0,2);
        if(led[1] || led[0]) $fatal(1,"UART clear failed");
        reset_button=1;repeat(10) @(negedge clk);
        if(in1 || led[3]) $fatal(1,"Button reset failed");
        $display("PASS top: UART-to-PWM integration, synchronized arm/fault, stop, clear, reset");$finish;
    end
endmodule
