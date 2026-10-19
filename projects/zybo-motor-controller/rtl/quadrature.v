`timescale 1ns/1ps
module quadrature #(
    parameter integer INVERT = 0
)(input wire clk, reset, a, b,
  output reg signed [1:0] step = 0,
  output reg illegal = 0,
  output reg [7:0] invalid_count = 0);
    (* ASYNC_REG = "TRUE" *) reg [1:0] enc_meta = 0, enc_sync = 0;
    reg [1:0] previous = 0;
    reg [2:0] startup = 0;
    function signed [1:0] decode;
        input [3:0] transition;
        begin
            case (transition)
                4'b0001,4'b0111,4'b1110,4'b1000: decode = 1;
                4'b0010,4'b1011,4'b1101,4'b0100: decode = -1;
                default: decode = 0;
            endcase
        end
    endfunction
    wire signed [1:0] decoded = decode({previous,enc_sync});
    always @(posedge clk) begin
        enc_meta <= {a,b};
        enc_sync <= enc_meta;
        step <= 0;
        illegal <= 0;
        if (reset) begin
            previous <= enc_sync;
            startup <= 0;
            invalid_count <= 0;
        end else if (startup < 4) begin
            startup <= startup + 1;
            previous <= enc_sync;
        end else begin
            previous <= enc_sync;
            step <= INVERT ? -decoded : decoded;
            if ((previous ^ enc_sync) == 2'b11) begin
                illegal <= 1;
                if (invalid_count != 255) invalid_count <= invalid_count + 1;
            end
        end
    end
endmodule
