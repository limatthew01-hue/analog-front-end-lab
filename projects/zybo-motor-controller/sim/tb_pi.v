`timescale 1ns/1ps
module tb_pi;
    reg clk=0, reset=1, tick=0, enable=0;
    reg [15:0] target=0;
    reg signed [15:0] measured=0;
    wire [9:0] duty;
    integer f,rc,en,t,m,expected,n=0;
    always #5 clk=~clk;
    pi_controller dut(.clk(clk),.reset(reset),.tick(tick),.enable(enable),
        .target_rpm(target),.measured_rpm_x10(measured),.duty_permille(duty));
    initial begin
        f=$fopen("build/pi_vectors.txt","r");
        if(!f) $fatal(1,"Missing reference vectors");
        repeat(3) @(negedge clk); reset=0;
        while(!$feof(f)) begin
            rc=$fscanf(f,"%d %d %d %d\n",en,t,m,expected);
            if(rc==4) begin
                enable=en;target=t;measured=m;tick=1;
                @(posedge clk); #1;
                if(duty!=expected) $fatal(1,"PI vector %0d expected %0d got %0d",n,expected,duty);
                @(negedge clk); tick=0; n=n+1;
            end
        end
        $display("PASS pi: %0d fixed-point vectors including saturation and stop",n); $finish;
    end
endmodule
