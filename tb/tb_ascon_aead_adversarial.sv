`timescale 1ns/1ps
// Phase 7B RTL *observations* versus independent Python oracle vectors.
// Never treats changed ciphertext/tag as proof of receiver-side tag acceptance.
module tb_ascon_aead_adversarial;
    logic clk = 1'b0;
    always #5 clk = ~clk;
    logic rst_n = 1'b0, start_i = 1'b0;
    logic [127:0] key_i = '0, nonce_i = '0;
    logic [127:0] associated_data_i = '0, plaintext_i = '0;
    logic [4:0] ad_len_i = '0, msg_len_i = '0;
    logic attack_enable_i = 1'b0;
    logic [2:0] attack_phase_i = '0;
    logic first_arm_i = 1'b0, replay_arm_i = 1'b0;
    logic [3:0] first_round_i = '0, replay_round_i = '0;
    logic [8:0] first_bit_i = '0, replay_bit_i = '0;
    logic [1:0] checkpoint_mode_i = '0;
    logic [8:0] checkpoint_bit_i = '0;
    logic suppress_alarm_i = 1'b0;

    logic first_fired, replay_fired, checkpoint_fired;
    logic raw_mismatch, alarm, valid, busy, done;
    logic [127:0] ct, tag_value;
    ascon_aead_encrypt_adversarial dut (
        .clk(clk), .rst_n(rst_n), .start_i(start_i),
        .key_i(key_i), .nonce_i(nonce_i),
        .associated_data_i(associated_data_i), .ad_len_i(ad_len_i),
        .plaintext_i(plaintext_i), .msg_len_i(msg_len_i),
        .attack_enable_i(attack_enable_i), .attack_phase_i(attack_phase_i),
        .first_arm_i(first_arm_i), .first_round_i(first_round_i),
        .first_bit_i(first_bit_i), .replay_arm_i(replay_arm_i),
        .replay_round_i(replay_round_i), .replay_bit_i(replay_bit_i),
        .checkpoint_mode_i(checkpoint_mode_i), .checkpoint_bit_i(checkpoint_bit_i),
        .suppress_alarm_i(suppress_alarm_i),
        .first_applied_o(first_fired), .replay_applied_o(replay_fired),
        .checkpoint_applied_o(checkpoint_fired),
        .raw_mismatch_o(raw_mismatch), .fault_detected_o(alarm),
        .result_valid_o(valid), .ciphertext_o(ct), .tag_o(tag_value),
        .busy_o(busy), .done_o(done)
    );

    string path;
    integer fd, parsed, count, cycles;
    integer ad_len, msg_len, phase, enable, fa, fr, fb, ra, rr, rb;
    integer cp_mode, cp_bit, suppress;
    integer exp_first, exp_replay, exp_cp, exp_raw, exp_alarm, exp_valid, exp_wrong;
    logic [127:0] key_v, nonce_v, ad_v, msg_v;
    logic [127:0] gold_ct, gold_tag, expected_ct, expected_tag;
    bit is_wrong;

    initial begin
        if (!$value$plusargs("VECTORS=%s", path))
            $fatal(1, "Missing +VECTORS=<path>");
        fd = $fopen(path, "r");
        if (fd == 0) $fatal(1, "Cannot read %s", path);
        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        count = 0;
        while (!$feof(fd)) begin
            parsed = $fscanf(fd,
                "%h %h %d %h %d %h %d %d %d %d %d %d %d %d %d %d %d %h %h %d %d %d %d %d %d %h %h %d\n",
                key_v, nonce_v, ad_len, ad_v, msg_len, msg_v,
                phase, enable, fa, fr, fb, ra, rr, rb, cp_mode, cp_bit, suppress,
                gold_ct, gold_tag, exp_first, exp_replay, exp_cp, exp_raw,
                exp_alarm, exp_valid, expected_ct, expected_tag, exp_wrong);
            if (parsed == -1) break;
            if (parsed != 28)
                $fatal(1, "Malformed Phase 7B vector %0d (%0d fields)", count, parsed);
            key_i = key_v;
            nonce_i = nonce_v;
            associated_data_i = ad_v;
            plaintext_i = msg_v;
            ad_len_i = ad_len[4:0];
            msg_len_i = msg_len[4:0];
            attack_phase_i = phase[2:0];
            attack_enable_i = (enable != 0);
            first_arm_i = (fa != 0);
            first_round_i = fr[3:0];
            first_bit_i = fb[8:0];
            replay_arm_i = (ra != 0);
            replay_round_i = rr[3:0];
            replay_bit_i = rb[8:0];
            checkpoint_mode_i = cp_mode[1:0];
            checkpoint_bit_i = cp_bit[8:0];
            suppress_alarm_i = (suppress != 0);

            @(negedge clk);
            start_i = 1'b1;
            @(negedge clk);
            start_i = 1'b0;
            if (busy !== 1'b1 || valid !== 1'b0 ||
                ct !== 128'd0 || tag_value !== 128'd0)
                $fatal(1, "Case %0d did not start fail-closed", count);
            cycles = 0;
            while (done !== 1'b1 && cycles < 500) begin
                @(posedge clk); #1;
                cycles++;
                if (done !== 1'b1 &&
                    (valid !== 1'b0 || ct !== 128'd0 || tag_value !== 128'd0))
                    $fatal(1, "Case %0d exposed ciphertext or tag before DONE", count);
            end
            if (done !== 1'b1 || busy !== 1'b0)
                $fatal(1, "Case %0d did not finish, cycles=%0d", count, cycles);
            if (first_fired !== (exp_first != 0) ||
                replay_fired !== (exp_replay != 0) ||
                checkpoint_fired !== (exp_cp != 0) ||
                raw_mismatch !== (exp_raw != 0) ||
                alarm !== (exp_alarm != 0) ||
                valid !== (exp_valid != 0) ||
                ct !== expected_ct || tag_value !== expected_tag)
                $fatal(1, "Case %0d mismatch flags first=%b/%0d replay=%b/%0d cp=%b/%0d raw=%b/%0d alarm=%b/%0d valid=%b/%0d CT=%h/%h TAG=%h/%h",
                    count, first_fired, exp_first, replay_fired, exp_replay,
                    checkpoint_fired, exp_cp, raw_mismatch, exp_raw,
                    alarm, exp_alarm, valid, exp_valid,
                    ct, expected_ct, tag_value, expected_tag);
            is_wrong = valid && (ct !== gold_ct || tag_value !== gold_tag);
            if (is_wrong !== (exp_wrong != 0))
                $fatal(1, "Case %0d incorrect-release classification mismatch", count);
            if (alarm && (valid || ct !== 128'd0 || tag_value !== 128'd0))
                $fatal(1, "Case %0d failed closed after alarm", count);
            $display("RESULT %0d %0d %0d %0d %0d %0d %0d %0d %0d",
                count, first_fired, replay_fired, checkpoint_fired,
                raw_mismatch, alarm, valid, is_wrong, cycles);
            @(posedge clk); #1;
            if (done !== 1'b0) $fatal(1, "DONE pulse not one cycle in case %0d", count);
            count++;
        end
        $fclose(fd);
        $display("PASS: %0d bounded AEAD adversarial comparisons", count);
        $finish;
    end
endmodule
