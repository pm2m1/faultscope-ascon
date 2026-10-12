// Unprotected, one-round-per-clock Ascon p[8] / p[12] controller.
// start is sampled only when busy_o = 0 and rounds_i is 8 or 12.
// done_o is a one-clock pulse. state_o holds the completed result.
module ascon_permutation (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start_i,
    input  logic [3:0]   rounds_i,
    input  logic [319:0] state_i,
    output logic [319:0] state_o,
    output logic         busy_o,
    output logic         done_o
);
    logic [319:0] state_q;
    logic [3:0]   rounds_q;
    logic [3:0]   round_count_q;
    logic [3:0]   round_index;
    logic [7:0]   round_constant;
    logic [319:0] round_result;

    function automatic logic [7:0] rc(input logic [3:0] index);
        case (index)
            4'd0:  rc = 8'hf0;
            4'd1:  rc = 8'he1;
            4'd2:  rc = 8'hd2;
            4'd3:  rc = 8'hc3;
            4'd4:  rc = 8'hb4;
            4'd5:  rc = 8'ha5;
            4'd6:  rc = 8'h96;
            4'd7:  rc = 8'h87;
            4'd8:  rc = 8'h78;
            4'd9:  rc = 8'h69;
            4'd10: rc = 8'h5a;
            4'd11: rc = 8'h4b;
            default: rc = 8'h00;
        endcase
    endfunction

    assign round_index = round_count_q +
                         ((rounds_q == 4'd8) ? 4'd4 : 4'd0);
    assign round_constant = rc(round_index);

    ascon_round u_round (
        .state_i(state_q),
        .round_constant_i(round_constant),
        .state_o(round_result)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q       <= '0;
            state_o       <= '0;
            rounds_q      <= '0;
            round_count_q <= '0;
            busy_o        <= 1'b0;
            done_o        <= 1'b0;
        end else begin
            done_o <= 1'b0;

            if (!busy_o) begin
                if (start_i && ((rounds_i == 4'd8) || (rounds_i == 4'd12))) begin
                    state_q       <= state_i;
                    rounds_q      <= rounds_i;
                    round_count_q <= 4'd0;
                    busy_o        <= 1'b1;
                end
            end else begin
                state_q <= round_result;
                if (round_count_q == (rounds_q - 4'd1)) begin
                    state_o <= round_result;
                    busy_o  <= 1'b0;
                    done_o  <= 1'b1;
                end else begin
                    round_count_q <= round_count_q + 4'd1;
                end
            end
        end
    end
endmodule
