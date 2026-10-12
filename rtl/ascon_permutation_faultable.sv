// Research-only controlled pre-round transient fault injection.
// The reference baseline is intentionally left unchanged.
// One bit of the live state is inverted for exactly one round input.
// start is sampled only when busy_o = 0 and rounds_i is 8 or 12.
// done_o is a one-clock pulse. state_o holds the completed result.
module ascon_permutation_faultable (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start_i,
    input  logic [3:0]   rounds_i,
    input  logic [319:0] state_i,
    input  logic         fault_arm_i,
    input  logic [3:0]   fault_round_i,
    input  logic [8:0]   fault_bit_i,
    output logic         fault_fired_o,
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
    logic [319:0] round_input;
    logic [319:0] fault_mask;
    logic fault_arm_q;
    logic [3:0] fault_round_q;
    logic [8:0] fault_bit_q;
    logic fire_now;

    // round_count_q is zero-based within the selected p[8] or p[12].
    // Inject BEFORE the nonlinear round, exactly once per invocation.
    assign fire_now = busy_o && fault_arm_q && !fault_fired_o &&
                      (round_count_q == fault_round_q) &&
                      (fault_bit_q < 9'd320);
    always_comb begin
        fault_mask = '0;
        if (fire_now)
            fault_mask[fault_bit_q] = 1'b1;
    end
    assign round_input = state_q ^ fault_mask;

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
        .state_i(round_input),
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
            fault_arm_q <= 1'b0;
            fault_round_q <= '0;
            fault_bit_q <= '0;
            fault_fired_o <= 1'b0;
        end else begin
            done_o <= 1'b0;

            if (!busy_o) begin
                if (start_i && ((rounds_i == 4'd8) || (rounds_i == 4'd12))) begin
                    state_q       <= state_i;
                    rounds_q      <= rounds_i;
                    round_count_q <= 4'd0;
                    busy_o        <= 1'b1;
                    fault_arm_q   <= fault_arm_i;
                    fault_round_q <= fault_round_i;
                    fault_bit_q   <= fault_bit_i;
                    fault_fired_o <= 1'b0;
                end
            end else begin
                if (fire_now)
                    fault_fired_o <= 1'b1;
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
