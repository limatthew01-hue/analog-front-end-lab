`timescale 1ns/1ps
module tb_quadrature;
    reg clk=0, reset=1, a=1,b=1;
    wire signed [1:0] step;
    wire illegal;
    wire [7:0] invalid_count;
    integer total=0, errors=0, i;
    always #5 clk=~clk;
    quadrature dut (.clk(clk),.reset(reset),.a(a),.b(b),.step(step),.illegal(illegal),.invalid_count(invalid_count));
    always @(posedge clk) begin
        if(!reset) begin total=total+$signed(step); if(illegal) errors=errors+1; end
    end
    task state;
        input [1:0] value;
        begin @(negedge clk); {a,b}=value; repeat(8) @(negedge clk); end
    endtask
    initial begin
        repeat(4) @(negedge clk); reset=0;
        repeat(10) @(negedge clk);
        if(total!=0 || errors!=0) $fatal(1,"Startup invented motion");
        state(2'b10); state(0); state(1); state(3);
        if(total!=4) $fatal(1,"Forward count %0d",total);
        state(1); state(0); state(2); state(3);
        if(total!=0) $fatal(1,"Reverse count %0d",total);
        for(i=0;i<260;i=i+1) begin state(0); state(3); end
        if(total!=0 || invalid_count!=255) $fatal(1,"Invalid state must not move and must saturate");
        $display("PASS quadrature: startup, both directions, invalid transitions, saturation"); $finish;
    end
endmodule
