`timescale 1ns/1ps
// End-to-end bounded AEAD temporal recomputation testbench.
// Each case: baseline, protected without fault, protected armed.
// It rejects any pre-DONE exposure of externally valid ciphertext/tag.
module tb_ascon_temporal_campaign;
    logic clk = 1'b0;
    always #5 clk = ~clk;

    logic rst_n = 1'b0;
    logic baseline_start = 1'b0;
    logic protected_start = 1'b0;
    logic [127:0] key_i = '0, nonce_i = '0;
    logic [127:0] associated_data_i = '0, plaintext_i = '0;
    logic [4:0] ad_len_i = '0, msg_len_i = '0;
    logic fault_enable_i = 1'b0;
    logic [2:0] fault_phase_i = '0;
    logic [3:0] fault_round_i = '0;
    logic [8:0] fault_bit_i = '0;

    logic [127:0] baseline_ct, baseline_tag;
    logic baseline_busy, baseline_done;
    ascon_aead_encrypt_bounded baseline (
        .clk(clk), .rst_n(rst_n), .start_i(baseline_start),
        .key_i(key_i), .nonce_i(nonce_i),
        .associated_data_i(associated_data_i), .ad_len_i(ad_len_i),
        .plaintext_i(plaintext_i), .msg_len_i(msg_len_i),
        .ciphertext_o(baseline_ct), .tag_o(baseline_tag),
        .busy_o(baseline_busy), .done_o(baseline_done)
    );

    logic [127:0] protected_ct, protected_tag;
    logic protected_busy, protected_done;
    logic injected, alarm, valid;
    ascon_aead_encrypt_temporal defended (
        .clk(clk), .rst_n(rst_n), .start_i(protected_start),
        .key_i(key_i), .nonce_i(nonce_i),
        .associated_data_i(associated_data_i), .ad_len_i(ad_len_i),
        .plaintext_i(plaintext_i), .msg_len_i(msg_len_i),
        .fault_enable_i(fault_enable_i), .fault_phase_i(fault_phase_i),
        .fault_round_i(fault_round_i), .fault_bit_i(fault_bit_i),
        .fault_applied_o(injected), .fault_detected_o(alarm),
        .result_valid_o(valid),
        .ciphertext_o(protected_ct), .tag_o(protected_tag),
        .busy_o(protected_busy), .done_o(protected_done)
    );

    string vectors_path;
    integer fd, parsed, count;
    integer adlen, msglen, arm, phase, round_idx, bit_idx, expected_hit;
    integer base_cycles, clean_cycles, armed_cycles;
    logic [127:0] k, n, ad, msg, golden_ct, golden_tag;
    logic [127:0] ct, tag_value;
    logic hit, detected, output_valid;

    task automatic run_baseline(output integer duration);
        @(negedge clk);
        baseline_start = 1'b1;
        @(negedge clk);
        baseline_start = 1'b0;
        if (baseline_busy !== 1'b1)
            $fatal(1, "Baseline did not accept case %0d", count);
        duration = 0;
        while (baseline_done !== 1'b1 && duration < 400) begin
            @(posedge clk); #1;
            duration++;
        end
        if (baseline_done !== 1'b1 || baseline_busy !== 1'b0)
            $fatal(1, "Baseline timeout case %0d", count);
        if (baseline_ct !== golden_ct || baseline_tag !== golden_tag)
            $fatal(1, "Baseline ciphertext or tag mismatch case %0d", count);
        @(posedge clk); #1;
        if (baseline_done !== 1'b0)
            $fatal(1, "Baseline done pulse too long case %0d", count);
    endtask

    task automatic run_protected(
        input logic arm_fault,
        output logic [127:0] observed_c,
        output logic [127:0] observed_t,
        output logic observed_hit,
        output logic observed_alarm,
        output logic observed_valid,
        output integer duration
    );
        @(negedge clk);
        fault_enable_i = arm_fault;
        protected_start = 1'b1;
        @(negedge clk);
        protected_start = 1'b0;
        if (protected_busy !== 1'b1)
            $fatal(1, "Protected did not accept case %0d", count);
        if (valid !== 1'b0 || protected_ct !== 128'd0 || protected_tag !== 128'd0)
            $fatal(1, "Premature output or stale valid case %0d", count);
        duration = 0;
        while (protected_done !== 1'b1 && duration < 500) begin
            @(posedge clk); #1;
            duration++;
            if (protected_done !== 1'b1 &&
                (valid !== 1'b0 || protected_ct !== 128'd0 || protected_tag !== 128'd0))
                $fatal(1, "Output leaked before done case %0d", count);
        end
        if (protected_done !== 1'b1 || protected_busy !== 1'b0)
            $fatal(1, "Protected timeout case %0d", count);
        observed_c = protected_ct;
        observed_t = protected_tag;
        observed_hit = injected;
        observed_alarm = alarm;
        observed_valid = valid;
        @(posedge clk); #1;
        if (protected_done !== 1'b0)
            $fatal(1, "Protected done pulse too long case %0d", count);
    endtask

    initial begin
        if (!$value$plusargs("VECTORS=%s", vectors_path))
            $fatal(1, "Missing +VECTORS=<path>");
        fd = $fopen(vectors_path, "r");
        if (fd == 0)
            $fatal(1, "Cannot open %s", vectors_path);
        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        count = 0;
        while (!$feof(fd)) begin
            parsed = $fscanf(fd,
                "%h %h %d %h %d %h %h %h %d %d %d %d %d\n",
                k, n, adlen, ad, msglen, msg,
                golden_ct, golden_tag, arm, phase,
                round_idx, bit_idx, expected_hit);
            if (parsed == -1) break;
            if (parsed != 13)
                $fatal(1, "Malformed case %0d: %0d fields", count, parsed);

            key_i = k; nonce_i = n;
            associated_data_i = ad; ad_len_i = adlen[4:0];
            plaintext_i = msg; msg_len_i = msglen[4:0];
            fault_phase_i = phase[2:0];
            fault_round_i = round_idx[3:0];
            fault_bit_i = bit_idx[8:0];

            run_baseline(base_cycles);
            run_protected(1'b0, ct, tag_value, hit, detected, output_valid, clean_cycles);
            if (hit !== 1'b0 || detected !== 1'b0 || output_valid !== 1'b1)
                $fatal(1, "Unexpected alarm/invalid fault-free case %0d", count);
            if (ct !== golden_ct || tag_value !== golden_tag)
                $fatal(1, "Protected golden mismatch case %0d", count);
            if (clean_cycles <= base_cycles)
                $fatal(1, "Expected temporal latency overhead case %0d", count);

            run_protected(arm != 0, ct, tag_value, hit, detected, output_valid, armed_cycles);
            if (armed_cycles != clean_cycles)
                $fatal(1, "Injected configuration changed latency case %0d", count);
            if (hit !== (expected_hit != 0))
                $fatal(1, "Wrong fault-fired flag case %0d got=%0d expected=%0d", count, hit, expected_hit);
            if (expected_hit != 0) begin
                if (detected !== 1'b1 || output_valid !== 1'b0 ||
                    ct !== 128'd0 || tag_value !== 128'd0)
                    $fatal(1, "Failure to detect/block injected fault case %0d", count);
            end else begin
                if (detected !== 1'b0 || output_valid !== 1'b1 ||
                    ct !== golden_ct || tag_value !== golden_tag)
                    $fatal(1, "False alarm or false rejection case %0d", count);
            end

            $display("RESULT %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
                count, adlen, msglen, arm, phase, round_idx, bit_idx,
                expected_hit, detected, output_valid,
                base_cycles, clean_cycles, armed_cycles);
            count++;
        end
        $fclose(fd);
        $display("PASS: %0d protected AEAD comparisons", count);
        $finish;
    end
endmodule
