// Research-only temporal recomputation protection for Ascon p[8]/p[12].
// A single round engine is reused twice. Only the FIRST invocation can be
// instrumented with the Phase 4A pre-round one-bit fault; the REPLAY is clean.
// The initial 320-bit state and selected round count are checkpointed.
// A mismatch raises fault_detected_o and suppresses state_o (all-zero).
// LIMITATION: Does not model replay faults, correlated errors, corrupt
// checkpoints, faults in comparison/control logic, or physical injections.
module ascon_permutation_temporal (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start_i,
    input  logic [3:0]   rounds_i,
    input  logic [319:0] state_i,
    input  logic         fault_arm_i,
    input  logic [3:0]   fault_round_i,
    input  logic [8:0]   fault_bit_i,
    output logic         fault_fired_o,
    output logic         fault_detected_o,
    output logic [319:0] state_o,
    output logic         busy_o,
    output logic         done_o
);
    typedef enum logic [2:0] {
        IDLE, FIRST_START, FIRST_WAIT, REPLAY_START, REPLAY_WAIT
    } fsm_t;
    fsm_t fsm_q;

    logic [319:0] initial_state_q, first_result_q;
    logic [3:0] rounds_q, fault_round_q;
    logic [8:0] fault_bit_q;
    logic fault_arm_q, first_fault_fired_q;
    logic engine_start, engine_done, engine_busy, engine_fault_fired;
    logic [319:0] engine_result;

    assign busy_o = (fsm_q != IDLE);
    assign engine_start = (fsm_q == FIRST_START) || (fsm_q == REPLAY_START);

    ascon_permutation_faultable u_round_engine (
        .clk(clk), .rst_n(rst_n), .start_i(engine_start),
        .rounds_i(rounds_q), .state_i(initial_state_q),
        .fault_arm_i((fsm_q == FIRST_START) && fault_arm_q),
        .fault_round_i(fault_round_q), .fault_bit_i(fault_bit_q),
        .fault_fired_o(engine_fault_fired), .state_o(engine_result),
        .busy_o(engine_busy), .done_o(engine_done)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fsm_q <= IDLE;
            initial_state_q <= '0;
            first_result_q <= '0;
            rounds_q <= '0;
            fault_round_q <= '0;
            fault_bit_q <= '0;
            fault_arm_q <= 1'b0;
            first_fault_fired_q <= 1'b0;
            fault_fired_o <= 1'b0;
            fault_detected_o <= 1'b0;
            state_o <= '0;
            done_o <= 1'b0;
        end else begin
            done_o <= 1'b0;
            case (fsm_q)
                IDLE: if (start_i && (rounds_i == 4'd8 || rounds_i == 4'd12)) begin
                    initial_state_q <= state_i;
                    rounds_q <= rounds_i;
                    fault_arm_q <= fault_arm_i;
                    fault_round_q <= fault_round_i;
                    fault_bit_q <= fault_bit_i;
                    first_result_q <= '0;
                    first_fault_fired_q <= 1'b0;
                    fault_fired_o <= 1'b0;
                    fault_detected_o <= 1'b0;
                    state_o <= '0;
                    fsm_q <= FIRST_START;
                end
                FIRST_START: fsm_q <= FIRST_WAIT;
                FIRST_WAIT: if (engine_done) begin
                    first_result_q <= engine_result;
                    first_fault_fired_q <= engine_fault_fired;
                    fsm_q <= REPLAY_START;
                end
                REPLAY_START: fsm_q <= REPLAY_WAIT;
                REPLAY_WAIT: if (engine_done) begin
                    fault_fired_o <= first_fault_fired_q;
                    fault_detected_o <= (first_result_q != engine_result);
                    state_o <= (first_result_q == engine_result) ? engine_result : '0;
                    done_o <= 1'b1;
                    fsm_q <= IDLE;
                end
                default: fsm_q <= IDLE;
            endcase
        end
    end
endmodule
