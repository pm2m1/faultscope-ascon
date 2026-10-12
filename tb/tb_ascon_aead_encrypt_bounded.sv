`timescale 1ns/1ps
module tb_ascon_aead_encrypt_bounded;
    logic clk = 1'b0;
    always #5 clk = ~clk;

    logic rst_n = 1'b0;
    logic start_i = 1'b0;
    logic [127:0] key_i = '0, nonce_i = '0;
    logic [127:0] associated_data_i = '0, plaintext_i = '0;
    logic [4:0] ad_len_i = '0, msg_len_i = '0;
    logic [127:0] ciphertext_o, tag_o;
    logic busy_o, done_o;

    ascon_aead_encrypt_bounded dut (
        .clk(clk), .rst_n(rst_n), .start_i(start_i),
        .key_i(key_i), .nonce_i(nonce_i),
        .associated_data_i(associated_data_i), .ad_len_i(ad_len_i),
        .plaintext_i(plaintext_i), .msg_len_i(msg_len_i),
        .ciphertext_o(ciphertext_o), .tag_o(tag_o),
        .busy_o(busy_o), .done_o(done_o)
    );

    string vectors_path;
    integer fd, parsed, count, cycles;
    integer adlen, msglen;
    logic [127:0] k, n, ad, msg, expected_cipher, expected_tag;

    initial begin
        if (!$value$plusargs("VECTORS=%s", vectors_path))
            $fatal(1, "Missing +VECTORS=path");
        fd = $fopen(vectors_path, "r");
        if (fd == 0)
            $fatal(1, "Cannot open vectors: %s", vectors_path);

        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        count = 0;

        while (!$feof(fd)) begin
            parsed = $fscanf(fd, "%h %h %d %h %d %h %h %h\n",
                            k, n, adlen, ad, msglen, msg,
                            expected_cipher, expected_tag);
            if (parsed == -1)
                break;
            if (parsed != 8)
                $fatal(1, "Malformed vector %0d: got %0d fields", count, parsed);

            @(negedge clk);
            key_i = k;
            nonce_i = n;
            associated_data_i = ad;
            ad_len_i = adlen[4:0];
            plaintext_i = msg;
            msg_len_i = msglen[4:0];
            start_i = 1'b1;

            @(negedge clk);
            start_i = 1'b0;
            if (busy_o !== 1'b1)
                $fatal(1, "Controller did not accept vector %0d", count);

            cycles = 0;
            while (done_o !== 1'b1 && cycles < 125) begin
                @(posedge clk);
                #1;
                cycles++;
            end
            if (done_o !== 1'b1)
                $fatal(1, "Timeout for AEAD vector %0d", count);
            if (busy_o !== 1'b0)
                $fatal(1, "Busy asserted after done, vector %0d", count);
            if (ciphertext_o !== expected_cipher)
                $fatal(1, "Ciphertext mismatch for vector %0d: got %h expected %h",
                       count, ciphertext_o, expected_cipher);
            if (tag_o !== expected_tag)
                $fatal(1, "Tag mismatch for vector %0d: got %h expected %h",
                       count, tag_o, expected_tag);

            @(posedge clk);
            #1;
            if (done_o !== 1'b0)
                $fatal(1, "done_o must pulse once (vector %0d)", count);
            count++;
        end
        $fclose(fd);
        $display("PASS: %0d bounded AEAD encryptions matched Python golden vectors", count);
        $finish;
    end
endmodule
