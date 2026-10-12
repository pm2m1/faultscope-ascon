// Phase 7A ADVERSARIAL TEST FIXTURE, NOT A PRODUCTION COUNTERMEASURE.
// Independent first/replay pre-round bit flips; checkpoint corruption;
// comparator alarm suppression. The verified Phase 4B RTL is untouched.
// State layout: {x0,x1,x2,x3,x4}; bit 0 is x4[0].
// checkpoint_mode: 0=none, 1=shared checkpoint (both passes),
//                  2=replay-only checkpoint, 3=reserved (no effect).
// Comparator suppress is a *fault simulation control*, not a secure override.
module ascon_permutation_adversarial (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start_i,
    input  logic [3:0]   rounds_i,
    input  logic [319:0] state_i,
    input  logic         first_arm_i,
    input  logic [3:0]   first_round_i,
    input  logic [8:0]   first_bit_i,
    input  logic         replay_arm_i,
    input  logic [3:0]   replay_round_i,
    input  logic [8:0]   replay_bit_i,
    input  logic [1:0]   checkpoint_mode_i,
    input  logic [8:0]   checkpoint_bit_i,
    input  logic         suppress_alarm_i,
    output logic         first_fired_o,
    output logic         replay_fired_o,
    output logic         checkpoint_fired_o,
    output logic         raw_mismatch_o,
    output logic         fault_detected_o,
    output logic         result_valid_o,
    output logic [319:0] state_o,
    output logic         busy_o,
    output logic         done_o
);
    typedef enum logic [2:0] {
        IDLE, FIRST_START, FIRST_WAIT, REPLAY_START, REPLAY_WAIT
    } fsm_t;
    fsm_t fsm_q;

    logic [319:0] checkpoint_q, first_result_q, replay_input;
    logic [319:0] checkpoint_mask;
    logic [3:0] rounds_q, first_round_q, replay_round_q;
    logic [8:0] first_bit_q, replay_bit_q, checkpoint_bit_q;
    logic [1:0] checkpoint_mode_q;
    logic first_arm_q, replay_arm_q, suppress_alarm_q;
    logic first_fired_q;
    logic engine_start, engine_done, engine_busy, engine_fired;
    logic [319:0] engine_result, engine_input;
    logic raw_mismatch;

    assign busy_o = (fsm_q != IDLE);
    assign engine_start = (fsm_q == FIRST_START) || (fsm_q == REPLAY_START);
    always_comb begin
        checkpoint_mask = '0;
        if (checkpoint_bit_q < 9'd320)
            checkpoint_mask[checkpoint_bit_q] = 1'b1;
    end
    assign replay_input = checkpoint_q ^
        ((checkpoint_mode_q == 2'd2) ? checkpoint_mask : 320'd0);
    assign engine_input = (fsm_q == REPLAY_START) ? replay_input : checkpoint_q;

    ascon_permutation_faultable u_engine (
        .clk(clk), .rst_n(rst_n), .start_i(engine_start),
        .rounds_i(rounds_q), .state_i(engine_input),
        .fault_arm_i((fsm_q == FIRST_START) ? first_arm_q :
                     (fsm_q == REPLAY_START) ? replay_arm_q : 1'b0),
        .fault_round_i((fsm_q == FIRST_START) ? first_round_q : replay_round_q),
        .fault_bit_i((fsm_q == FIRST_START) ? first_bit_q : replay_bit_q),
        .fault_fired_o(engine_fired), .state_o(engine_result),
        .busy_o(engine_busy), .done_o(engine_done)
    );

    assign raw_mismatch = (first_result_q != engine_result);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fsm_q <= IDLE;
            checkpoint_q <= '0;
            first_result_q <= '0;
            rounds_q <= '0;
            first_arm_q <= 1'b0;
            replay_arm_q <= 1'b0;
            first_round_q <= '0;
            replay_round_q <= '0;
            first_bit_q <= '0;
            replay_bit_q <= '0;
            checkpoint_bit_q <= '0;
            checkpoint_mode_q <= '0;
            suppress_alarm_q <= 1'b0;
            first_fired_q <= 1'b0;
            first_fired_o <= 1'b0;
            replay_fired_o <= 1'b0;
            checkpoint_fired_o <= 1'b0;
            raw_mismatch_o <= 1'b0;
            fault_detected_o <= 1'b0;
            result_valid_o <= 1'b0;
            state_o <= '0;
            done_o <= 1'b0;
        end else begin
            done_o <= 1'b0;
            case (fsm_q)
                IDLE: if (start_i && (rounds_i == 4'd8 || rounds_i == 4'd12)) begin
                    // Shared checkpoint faults occur at capture, before BOTH runs.
                    // Replay-only faults occur at replay launch instead.
                    checkpoint_q <= state_i ^
                        ((checkpoint_mode_i == 2'd1 && checkpoint_bit_i < 9'd320)
                         ? (320'd1 << checkpoint_bit_i) : 320'd0);
                    rounds_q <= rounds_i;
                    first_arm_q <= first_arm_i;
                    replay_arm_q <= replay_arm_i;
                    first_round_q <= first_round_i;
                    replay_round_q <= replay_round_i;
                    first_bit_q <= first_bit_i;
                    replay_bit_q <= replay_bit_i;
                    checkpoint_mode_q <= checkpoint_mode_i;
                    checkpoint_bit_q <= checkpoint_bit_i;
                    suppress_alarm_q <= suppress_alarm_i;
                    first_result_q <= '0;
                    first_fired_q <= 1'b0;
                    first_fired_o <= 1'b0;
                    replay_fired_o <= 1'b0;
                    checkpoint_fired_o <=
                        ((checkpoint_mode_i == 2'd1 || checkpoint_mode_i == 2'd2)
                         && checkpoint_bit_i < 9'd320);
                    raw_mismatch_o <= 1'b0;
                    fault_detected_o <= 1'b0;
                    result_valid_o <= 1'b0;
                    state_o <= '0;
                    fsm_q <= FIRST_START;
                end
                FIRST_START: fsm_q <= FIRST_WAIT;
                FIRST_WAIT: if (engine_done) begin
                    first_result_q <= engine_result;
                    first_fired_q <= engine_fired;
                    fsm_q <= REPLAY_START;
                end
                REPLAY_START: fsm_q <= REPLAY_WAIT;
                REPLAY_WAIT: if (engine_done) begin
                    first_fired_o <= first_fired_q;
                    replay_fired_o <= engine_fired;
                    raw_mismatch_o <= raw_mismatch;
                    fault_detected_o <= raw_mismatch && !suppress_alarm_q;
                    result_valid_o <= !raw_mismatch || suppress_alarm_q;
                    // Original temporal engine outputs REPLAY state on match.
                    // Simulated comparator override releases that replay state
                    // even on mismatch (an intentional failure model).
                    state_o <= (!raw_mismatch || suppress_alarm_q)
                               ? engine_result : 320'd0;
                    done_o <= 1'b1;
                    fsm_q <= IDLE;
                end
                default: fsm_q <= IDLE;
            endcase
        end
    end
endmodule
