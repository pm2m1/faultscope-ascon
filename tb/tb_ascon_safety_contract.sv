`timescale 1ns/1ps
// Deterministic positive test of a separate SVA monitor attached to live RTL.
module tb_ascon_safety_contract;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start_i = 0, fault_enable_i = 0;
    logic [127:0] key_i = 128'h00112233445566778899aabbccddeeff;
    logic [127:0] nonce_i = 128'hffeeddccbbaa99887766554433221100;
    logic [127:0] associated_data_i = 128'h1122334455667788;
    logic [4:0] ad_len_i = 5'd7, msg_len_i = 5'd8;
    logic [127:0] plaintext_i = 128'h1234567890abcdef;
    logic [2:0] fault_phase_i = 0;
    logic [3:0] fault_round_i = 0;
    logic [8:0] fault_bit_i = 0;
    logic fault_applied_o, fault_detected_o, result_valid_o;
    logic [127:0] ciphertext_o, tag_o;
    logic busy_o, done_o;

    ascon_aead_encrypt_temporal dut (
        .clk(clk), .rst_n(rst_n), .start_i(start_i),
        .key_i(key_i), .nonce_i(nonce_i),
        .associated_data_i(associated_data_i), .ad_len_i(ad_len_i),
        .plaintext_i(plaintext_i), .msg_len_i(msg_len_i),
        .fault_enable_i(fault_enable_i), .fault_phase_i(fault_phase_i),
        .fault_round_i(fault_round_i), .fault_bit_i(fault_bit_i),
        .fault_applied_o(fault_applied_o), .fault_detected_o(fault_detected_o),
        .result_valid_o(result_valid_o), .ciphertext_o(ciphertext_o), .tag_o(tag_o),
        .busy_o(busy_o), .done_o(done_o)
    );

    ascon_temporal_safety_contract contract (
        .clk(clk), .rst_n(rst_n),
        .fault_detected_o(fault_detected_o),
        .result_valid_o(result_valid_o),
        .ciphertext_o(ciphertext_o), .tag_o(tag_o),
        .busy_o(busy_o), .done_o(done_o)
    );

    task automatic transaction(input logic inject, input logic [4:0] ad_len,
                                input logic [4:0] msg_len);
        integer ticks;
        @(negedge clk);
        fault_enable_i = inject;
        ad_len_i = ad_len;
        msg_len_i = msg_len;
        start_i = 1'b1;
        @(negedge clk);
        start_i = 1'b0;
        if (!busy_o) $fatal(1, "Transaction did not enter busy state");
        ticks = 0;
        while (!done_o && ticks < 600) begin
            @(posedge clk); #1;
            ticks++;
        end
        if (!done_o) $fatal(1, "Contract campaign timed out");
        if (fault_detected_o !== inject) $fatal(1, "Alarm differed from expected injection");
        if (fault_applied_o !== inject) $fatal(1, "Fault event differed from expected injection");
        if (result_valid_o !== !inject) $fatal(1, "Invalid output policy");
        if (inject && (ciphertext_o !== 128'd0 || tag_o !== 128'd0))
            $fatal(1, "Alarm produced nonzero output");
        @(posedge clk); #1;
        if (done_o) $fatal(1, "Done pulse lasted more than a cycle");
    endtask

    initial begin
        repeat (3) @(negedge clk);
        rst_n = 1;
        // Normal, faulted, recovery, and 16-byte boundary processing.
        transaction(1'b0, 5'd0, 5'd0);
        transaction(1'b1, 5'd7, 5'd8);
        transaction(1'b0, 5'd16, 5'd16);
        $display("PASS: temporal RTL safety assertions (normal, detected fault, restart)");
        $finish;
    end
endmodule
