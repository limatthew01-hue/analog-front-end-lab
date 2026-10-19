`timescale 1ns/1ps
// Accelerated clock; real control period, encoder CPR, and mechanical time constant.
// PWM is 1 kHz here (200 clocks/frame); production top uses 20 kHz / 125 MHz.
module tb_closed_loop;
    reg clk=0,reset=1,arm=0,a=0,b=0,valid=0,en=0;
    reg [15:0] target=0;
    wire pwm_out,active,alive,tick,requested;
    wire [9:0] duty;
    wire signed [15:0] measured;
    wire [15:0] requested_target;
    wire [7:0] faults,invalid;
    integer cycles=0, f, state_index=0, count_position=0, new_position;
    real speed=0.0,position=0.0,load=0.0, equilibrium;
    always #2500 clk=~clk;
    motor_core #(.CLK_HZ(200000),.PWM_HZ(1000)) dut (
        .clk(clk),.reset(reset),.arm(arm),.driver_fault_n(1'b1),.encoder_a(a),.encoder_b(b),
        .cmd_valid(valid),.cmd_enable(en),.cmd_clear(1'b0),.cmd_target(target),
        .pwm_out(pwm_out),.active(active),.link_alive(alive),.control_tick(tick),
        .duty_permille(duty),.measured_rpm_x10(measured),.target_rpm(requested_target),
        .requested_enable(requested),.faults(faults),.invalid_count(invalid));
    always @(negedge clk) begin
        if(!reset) begin
            if ((^duty === 1'bx) || (^measured === 1'bx) || (pwm_out === 1'bx))
                $fatal(1,"Undefined closed-loop state");
            cycles=cycles+1;
            load=(cycles>=400000 && cycles<800000) ? 90.0 : 0.0;
            equilibrium=(pwm_out ? 720.0 : 0.0)-load;
            speed=speed+(equilibrium-speed)*0.000005/0.12;
            if(speed<0) speed=0;
            position=position+speed*0.000005*358.331/60.0;
            new_position=$rtoi(position);
            if(new_position>count_position) begin
                count_position=new_position;state_index=(state_index+1)%4;
                case(state_index) 0:{a,b}=0;1:{a,b}=1;2:{a,b}=3;3:{a,b}=2;endcase
            end
            valid=cycles%20000==1;
            en=cycles>=20000 && cycles<800000;
            target=en ? 300 : 0;
            if(cycles==780000 && (speed<295 || speed>305)) $fatal(1,"Loaded speed did not converge: %f",speed);
            if(faults!=0) $fatal(1,"Unexpected fault %0d",faults);
            if(cycles>=1000000) begin
                if(active || pwm_out) $fatal(1,"Stop failed");
                $fclose(f);$display("PASS closed loop: switched-PWM plant, encoder feedback, load change, stop");$finish;
            end
        end
    end
    always @(posedge clk) if(!reset && tick) begin
        #1;
        $fwrite(f,"%.6f,%0d,%.6f,%.1f,%0d,%.1f,%0d,%0d\n",
            cycles*0.000005,requested_target,speed,measured/10.0,
            active ? duty : 0,load,active,faults);
    end
    initial begin
        f=$fopen("results/rtl_closed_loop.csv","w");
        $fwrite(f,"time_s,target_rpm,plant_rpm,measured_rpm,duty_permille,load_rpm,active,faults\n");
        repeat(10) @(negedge clk);reset=0;arm=1;
    end
endmodule
