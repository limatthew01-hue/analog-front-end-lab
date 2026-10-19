`timescale 1ns/1ps
module tb_serial;
    reg clk=0,reset=1,rx=1;
    wire tx,valid,en,clear;
    wire [15:0] target;
    wire [7:0] tx_byte;
    wire tx_valid;
    integer accepted=0, packets=0, k;
    reg [7:0] bytes_in[0:11];
    reg [7:0] c;
    always #5 clk=~clk;
    serial_link #(.CLK_HZ(160000),.BAUD(10000),.TELEMETRY_HZ(20)) dut (
        .clk(clk),.reset(reset),.rx(rx),.tx(tx),.cmd_valid(valid),.cmd_enable(en),
        .cmd_clear(clear),.cmd_target(target),.rpm_x10(-16'sd123),.target_rpm(16'd300),
        .duty(10'd417),.status(8'd7),.faults(8'd0),.invalid_count(8'd2));
    uart_rx #(.CLKS_PER_BIT(16)) monitor(.clk(clk),.reset(reset),.rx(tx),.data(tx_byte),.valid(tx_valid));
    function [7:0] crc;
        input [7:0] old,value;
        reg [7:0] result;
        integer i;
        begin result=old^value;
            for(i=0;i<8;i=i+1) result=result[7] ? (result<<1)^8'h07 : result<<1;
            crc=result;
        end
    endfunction
    always @(posedge clk) begin
        if(valid) accepted=accepted+1;
        if(tx_valid) begin
            bytes_in[packets%12]=tx_byte;
            if(packets%12==11) begin
                c=0;
                for(k=0;k<11;k=k+1) c=crc(c,bytes_in[k]);
                if(c!=tx_byte || bytes_in[0]!=8'h5a ||
                    {bytes_in[3],bytes_in[2]}!=16'hff85 ||
                    {bytes_in[5],bytes_in[4]}!=300 ||
                    {bytes_in[7],bytes_in[6]}!=417 ||
                    bytes_in[8]!=7 || bytes_in[9]!=0 || bytes_in[10]!=2)
                    $fatal(1,"Telemetry snapshot/CRC failed");
            end
            packets=packets+1;
        end
    end
    task send_byte;
        input [7:0] value;
        integer bit_n;
        begin
            rx=0; repeat(16) @(negedge clk);
            for(bit_n=0;bit_n<8;bit_n=bit_n+1) begin rx=value[bit_n]; repeat(16) @(negedge clk); end
            rx=1; repeat(16) @(negedge clk);
        end
    endtask
    task frame;
        input [15:0] speed;
        input [7:0] flags;
        input integer damage;
        reg [7:0] check;
        begin
            check=crc(crc(crc(crc(crc(0,8'ha5),8'ha5),speed[7:0]),speed[15:8]),flags);
            send_byte(8'ha5);send_byte(8'ha5);send_byte(speed[7:0]);send_byte(speed[15:8]);send_byte(flags);
            send_byte(damage ? check^8'h01 : check);
            repeat(10) @(negedge clk);
        end
    endtask
    initial begin
        repeat(10) @(negedge clk);reset=0;
        frame(300,1,0);
        if(accepted!=1 || target!=300 || !en) $fatal(1,"Good command failed");
        frame(400,1,1); frame(601,1,0); frame(100,4,0); frame(100,3,0);
        if(accepted!=1 || target!=300) $fatal(1,"Invalid command accepted");
        frame(165,1,0); // Embedded sync value 0xA5 is legal in payload.
        if(accepted!=2 || target!=165) $fatal(1,"Payload sync caused resynchronization");
        send_byte(8'ha5);send_byte(1);repeat(3400) @(negedge clk);
        frame(0,2,0);
        if(accepted!=3 || target!=0 || en || !clear) $fatal(1,"Truncated-frame timeout/clear failed");
        // Bad UART stop bit must not make a valid command.
        rx=0; repeat(180) @(negedge clk); rx=1;repeat(3500) @(negedge clk);
        frame(0,0,0);
        if(accepted!=4) $fatal(1,"Framing error recovery failed");
        repeat(18000) @(negedge clk);
        if(packets<12) $fatal(1,"No telemetry received");
        $display("PASS serial: CRC, bounds, flags, truncation, UART framing, telemetry snapshot");$finish;
    end
endmodule
