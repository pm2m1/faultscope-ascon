// Fault-instrumented copy of bounded Ascon AEAD controller (research only).
// Baseline rtl/ascon_aead_encrypt_bounded.sv remains unchanged.
// Input buses: byte 0 is bits [7:0], byte 15 is bits [127:120].
// Output: ciphertext_o low msg_len_i bytes; tag_o low byte first.
// Constraints: 0 <= msg_len_i, ad_len_i <= 16, one transaction at a time.
// This is not an authenticated decryption interface or production-hardened RTL.
// Depends on existing ascon_permutation.sv and ascon_round.sv.
module ascon_aead_encrypt_faultable (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start_i,
    input  logic [127:0] key_i,
    input  logic [127:0] nonce_i,
    input  logic [127:0] associated_data_i,
    input  logic [4:0]   ad_len_i,
    input  logic [127:0] plaintext_i,
    input  logic [4:0]   msg_len_i,
    // Phase: 0 init p12, 1 first AD p8, 2 AD full-block pad p8,
    //        3 full-message p8, 4 final p12.
    // Round number is zero-based within the selected permutation.
    // Bit 0 is the least significant bit of x4; bit 319 is the MSB of x0.
    input  logic         fault_enable_i,
    input  logic [2:0]   fault_phase_i,
    input  logic [3:0]   fault_round_i,
    input  logic [8:0]   fault_bit_i,
    output logic         fault_applied_o,
    output logic [127:0] ciphertext_o,
    output logic [127:0] tag_o,
    output logic         busy_o,
    output logic         done_o
);
    localparam logic [63:0] IV = 64'h00001000808c0001;
    typedef enum logic [3:0] {
        IDLE, INIT_START, INIT_WAIT, POST_INIT, AD_PREP,
        AD_START, AD_WAIT, AD_PAD_FULL, DOMAIN_SEPARATE,
        MSG_FULL, MSG_START, MSG_WAIT, MSG_TAIL,
        FINAL_PREP, FINAL_START, FINAL_WAIT
    } fsm_t;

    fsm_t fsm_q;
    logic [319:0] ascon_state_q;
    logic [127:0] key_q, nonce_q, ad_q, msg_q;
    logic [4:0] ad_len_q, msg_len_q;
    logic ad_full_q;
    logic ad_padding_pass_q;
    logic fault_enable_q;
    logic [2:0] fault_phase_q;
    logic [3:0] fault_round_q;
    logic [8:0] fault_bit_q;
    logic [2:0] active_phase;
    logic perm_fault_arm, perm_fault_fired;

    always_comb begin
        case (fsm_q)
            INIT_START:  active_phase = 3'd0;
            AD_START:    active_phase = ad_padding_pass_q ? 3'd2 : 3'd1;
            MSG_START:   active_phase = 3'd3;
            FINAL_START: active_phase = 3'd4;
            default:     active_phase = 3'd7;
        endcase
    end
    assign perm_fault_arm = fault_enable_q && (active_phase == fault_phase_q);

    logic [127:0] ad_padded;
    logic [127:0] msg_masked, msg_valid_mask, msg_padding;
    logic [127:0] ad_to_xor;
    logic [127:0] current_rate, full_cipher;

    logic perm_start, perm_busy, perm_done;
    logic [3:0] perm_rounds;
    logic [319:0] perm_state_out;

    assign busy_o = (fsm_q != IDLE);
    assign perm_start = (fsm_q == INIT_START) || (fsm_q == AD_START) ||
                        (fsm_q == MSG_START) || (fsm_q == FINAL_START);
    assign perm_rounds = ((fsm_q == AD_START) || (fsm_q == MSG_START))
                         ? 4'd8 : 4'd12;

    ascon_permutation_faultable u_permutation (
        .clk(clk), .rst_n(rst_n), .start_i(perm_start),
        .rounds_i(perm_rounds), .state_i(ascon_state_q),
        .fault_arm_i(perm_fault_arm),
        .fault_round_i(fault_round_q), .fault_bit_i(fault_bit_q),
        .fault_fired_o(perm_fault_fired),
        .state_o(perm_state_out), .busy_o(perm_busy), .done_o(perm_done)
    );

    // Use bounded loops instead of out-of-range variable part selects.
    // For full 16-byte AD, another p[8] is needed for the final padding block.
    always_comb begin
        ad_padded = '0;
        msg_masked = '0;
        msg_valid_mask = '0;
        msg_padding = '0;
        for (int i = 0; i < 16; i++) begin
            if (i < ad_len_q)
                ad_padded[8*i +: 8] = ad_q[8*i +: 8];
            else if (i == ad_len_q)
                ad_padded[8*i +: 8] = 8'h01;

            if (i < msg_len_q) begin
                msg_masked[8*i +: 8] = msg_q[8*i +: 8];
                msg_valid_mask[8*i +: 8] = 8'hff;
            end else if (i == msg_len_q) begin
                msg_padding[8*i +: 8] = 8'h01;
            end
        end
        ad_to_xor = (ad_len_q == 5'd16) ? ad_q : ad_padded;
        current_rate = {ascon_state_q[255:192], ascon_state_q[319:256]};
        full_cipher = current_rate ^ msg_q;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fsm_q <= IDLE;
            ascon_state_q <= '0;
            key_q <= '0;
            nonce_q <= '0;
            ad_q <= '0;
            msg_q <= '0;
            ad_len_q <= '0;
            msg_len_q <= '0;
            ad_full_q <= 1'b0;
            ad_padding_pass_q <= 1'b0;
            fault_enable_q <= 1'b0;
            fault_phase_q <= '0;
            fault_round_q <= '0;
            fault_bit_q <= '0;
            fault_applied_o <= 1'b0;
            ciphertext_o <= '0;
            tag_o <= '0;
            done_o <= 1'b0;
        end else begin
            done_o <= 1'b0;
            case (fsm_q)
                IDLE: begin
                    // Invalid lengths are ignored; no state or output is changed.
                    if (start_i && ad_len_i <= 5'd16 && msg_len_i <= 5'd16) begin
                        key_q <= key_i;
                        nonce_q <= nonce_i;
                        ad_q <= associated_data_i;
                        msg_q <= plaintext_i;
                        ad_len_q <= ad_len_i;
                        msg_len_q <= msg_len_i;
                        ad_full_q <= 1'b0;
                        ad_padding_pass_q <= 1'b0;
                        fault_enable_q <= fault_enable_i;
                        fault_phase_q <= fault_phase_i;
                        fault_round_q <= fault_round_i;
                        fault_bit_q <= fault_bit_i;
                        fault_applied_o <= 1'b0;
                        ciphertext_o <= '0;
                        tag_o <= '0;
                        ascon_state_q <= {
                            IV,
                            key_i[63:0], key_i[127:64],
                            nonce_i[63:0], nonce_i[127:64]
                        };
                        fsm_q <= INIT_START;
                    end
                end
                INIT_START: fsm_q <= INIT_WAIT;
                INIT_WAIT: if (perm_done) begin
                    if (perm_fault_fired) fault_applied_o <= 1'b1;
                    ascon_state_q <= perm_state_out;
                    fsm_q <= POST_INIT;
                end
                POST_INIT: begin
                    // XOR K0 into x3 and K1 into x4.
                    ascon_state_q <= ascon_state_q ^
                        {192'd0, key_q[63:0], key_q[127:64]};
                    fsm_q <= AD_PREP;
                end
                AD_PREP: begin
                    if (ad_len_q == 0) begin
                        fsm_q <= DOMAIN_SEPARATE;
                    end else begin
                        ascon_state_q <= {
                            ascon_state_q[319:256] ^ ad_to_xor[63:0],
                            ascon_state_q[255:192] ^ ad_to_xor[127:64],
                            ascon_state_q[191:0]
                        };
                        ad_full_q <= (ad_len_q == 5'd16);
                        fsm_q <= AD_START;
                    end
                end
                AD_START: fsm_q <= AD_WAIT;
                AD_WAIT: if (perm_done) begin
                    if (perm_fault_fired) fault_applied_o <= 1'b1;
                    ascon_state_q <= perm_state_out;
                    fsm_q <= ad_full_q ? AD_PAD_FULL : DOMAIN_SEPARATE;
                end
                AD_PAD_FULL: begin
                    // An exact full AD block needs a *separate* padded final block.
                    ascon_state_q[319:256] <= ascon_state_q[319:256] ^ 64'h1;
                    ad_full_q <= 1'b0;
                    ad_padding_pass_q <= 1'b1;
                    fsm_q <= AD_START;
                end
                DOMAIN_SEPARATE: begin
                    ascon_state_q[63:0] <= ascon_state_q[63:0] ^ 64'h8000000000000000;
                    fsm_q <= (msg_len_q == 5'd16) ? MSG_FULL : MSG_TAIL;
                end
                MSG_FULL: begin
                    // Full 16-byte plaintext: output whole rate, then run p[8].
                    ciphertext_o <= full_cipher;
                    ascon_state_q <= {
                        ascon_state_q[319:256] ^ msg_q[63:0],
                        ascon_state_q[255:192] ^ msg_q[127:64],
                        ascon_state_q[191:0]
                    };
                    fsm_q <= MSG_START;
                end
                MSG_START: fsm_q <= MSG_WAIT;
                MSG_WAIT: if (perm_done) begin
                    if (perm_fault_fired) fault_applied_o <= 1'b1;
                    ascon_state_q <= perm_state_out;
                    fsm_q <= MSG_TAIL;
                end
                MSG_TAIL: begin
                    if (msg_len_q == 5'd16) begin
                        // After the full-block permutation, final tail is empty.
                        ascon_state_q[319:256] <= ascon_state_q[319:256] ^ 64'h1;
                    end else begin
                        ciphertext_o <= (current_rate ^ msg_q) & msg_valid_mask;
                        ascon_state_q <= {
                            ascon_state_q[319:256] ^ msg_masked[63:0] ^ msg_padding[63:0],
                            ascon_state_q[255:192] ^ msg_masked[127:64] ^ msg_padding[127:64],
                            ascon_state_q[191:0]
                        };
                    end
                    fsm_q <= FINAL_PREP;
                end
                FINAL_PREP: begin
                    // XOR K0 into x2, K1 into x3.
                    ascon_state_q <= {
                        ascon_state_q[319:192],
                        ascon_state_q[191:128] ^ key_q[63:0],
                        ascon_state_q[127:64] ^ key_q[127:64],
                        ascon_state_q[63:0]
                    };
                    fsm_q <= FINAL_START;
                end
                FINAL_START: fsm_q <= FINAL_WAIT;
                FINAL_WAIT: if (perm_done) begin
                    if (perm_fault_fired) fault_applied_o <= 1'b1;
                    // Compute tag bytes: LE(x3 ^ K0) || LE(x4 ^ K1).
                    tag_o <= {
                        perm_state_out[63:0] ^ key_q[127:64],
                        perm_state_out[127:64] ^ key_q[63:0]
                    };
                    done_o <= 1'b1;
                    fsm_q <= IDLE;
                end
                default: fsm_q <= IDLE;
            endcase
        end
    end
endmodule
