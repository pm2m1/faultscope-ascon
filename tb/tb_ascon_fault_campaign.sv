`timescale 1ns/1ps
// The experiment runs each vector twice: fault disabled, then armed.
// Golden software output and faulted software output are both checked.
module tb_ascon_fault_campaign;
    logic clk = 1'b0;
    always #5 clk = ~clk;

    logic rst_n = 1'b0;
    logic start_i = 1'b0;
    logic [127:0] key_i = '0, nonce_i = '0;
    logic [127:0] associated_data_i = '0, plaintext_i = '0;
    logic [4:0] ad_len_i = '0, msg_len_i = '0;
    logic fault_enable_i = 1'b0;
    logic [2:0] fault_phase_i = '0;
    logic [3:0] fault_round_i = '0;
    logic [8:0] fault_bit_i = '0;
    logic [127:0] ciphertext_o, tag_o;
    logic busy_o, done_o, fault_applied_o;

    ascon_aead_encrypt_faultable dut (
        .clk(clk), .rst_n(rst_n), .start_i(start_i),
        .key_i(key_i), .nonce_i(nonce_i),
        .associated_data_i(associated_data_i), .ad_len_i(ad_len_i),
        .plaintext_i(plaintext_i), .msg_len_i(msg_len_i),
        .fault_enable_i(fault_enable_i), .fault_phase_i(fault_phase_i),
        .fault_round_i(fault_round_i), .fault_bit_i(fault_bit_i),
        .fault_applied_o(fault_applied_o),
        .ciphertext_o(ciphertext_o), .tag_o(tag_o),
        .busy_o(busy_o), .done_o(done_o)
    );

    string vectors_path;
    integer fd, parsed, count;
    integer adlen, msglen, arm, phase, round_idx, bit_idx, expected_hit;
    integer baseline_cycles, fault_cycles;
    logic [127:0] k, n, ad, msg;
    logic [127:0] expected_cipher, expected_tag;
    logic [127:0] expected_fault_cipher, expected_fault_tag;
    logic [127:0] observed_cipher, observed_tag;
    logic observed_hit;

    task automatic run_once(
        input logic enable,
        output logic [127:0] observed_c,
        output logic [127:0] observed_t,
        output logic hit,
        output integer duration
    );
        @(negedge clk);
        fault_enable_i = enable;
        start_i = 1'b1;
        @(negedge clk);
        start_i = 1'b0;
        if (busy_o !== 1'b1)
            $fatal(1, "Controller did not accept case %0d", count);

        duration = 0;
        while (done_o !== 1'b1 && duration < 160) begin
            @(posedge clk);
            #1;
            duration++;
        end
        if (done_o !== 1'b1)
            $fatal(1, "Timeout case %0d fault=%0d", count, enable);
        if (busy_o !== 1'b0)
            $fatal(1, "Busy after done case %0d", count);

        observed_c = ciphertext_o;
        observed_t = tag_o;
        hit = fault_applied_o;

        @(posedge clk);
        #1;
        if (done_o !== 1'b0)
            $fatal(1, "done_o pulse too long case %0d", count);
    endtask

    initial begin
        if (!$value$plusargs("VECTORS=%s", vectors_path))
            $fatal(1, "Missing +VECTORS=<path>");
        fd = $fopen(vectors_path, "r");
        if (fd == 0)
            $fatal(1, "Cannot open vectors %s", vectors_path);

        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        count = 0;

        while (!$feof(fd)) begin
            parsed = $fscanf(fd,
                "%h %h %d %h %d %h %h %h %d %d %d %d %d %h %h\n",
                k, n, adlen, ad, msglen, msg,
                expected_cipher, expected_tag, arm, phase,
                round_idx, bit_idx, expected_hit,
                expected_fault_cipher, expected_fault_tag);
            if (parsed == -1) break;
            if (parsed != 15)
                $fatal(1, "Malformed case %0d: read %0d fields", count, parsed);
            key_i = k;
            nonce_i = n;
            associated_data_i = ad;
            ad_len_i = adlen[4:0];
            plaintext_i = msg;
            msg_len_i = msglen[4:0];
            fault_phase_i = phase[2:0];
            fault_round_i = round_idx[3:0];
            fault_bit_i = bit_idx[8:0];

            run_once(1'b0, observed_cipher, observed_tag,
                     observed_hit, baseline_cycles);
            if (observed_hit !== 1'b0)
                $fatal(1, "False fault-applied indication case %0d", count);
            if (observed_cipher !== expected_cipher || observed_tag !== expected_tag)
                $fatal(1, "Baseline mismatch case %0d", count);

            run_once(arm != 0, observed_cipher, observed_tag,
                     observed_hit, fault_cycles);
            if (observed_hit !== (expected_hit != 0))
                $fatal(1, "Injection hit mismatch case %0d got %0d expected %0d",
                       count, observed_hit, expected_hit);
            if (observed_cipher !== expected_fault_cipher ||
                observed_tag !== expected_fault_tag)
                $fatal(1,
                    "Faulted output mismatch case %0d: ct %032h expected %032h, tag %032h expected %032h",
                    count, observed_cipher, expected_fault_cipher,
                    observed_tag, expected_fault_tag);
            if (fault_cycles != baseline_cycles)
                $fatal(1, "Fault injector changed controller latency case %0d", count);

            $display("RESULT %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
                     count, adlen, msglen, arm, phase, round_idx, bit_idx,
                     expected_hit, (observed_cipher != expected_cipher),
                     (observed_tag != expected_tag), fault_cycles);
            count++;
        end
        $fclose(fd);
        $display("PASS: %0d bounded fault-injection comparisons matched software model", count);
        $finish;
    end
endmodule
