`timescale 1ns/1ps
module tb_ascon_permutation;
    logic clk = 1'b0;
    always #5 clk = ~clk;

    logic rst_n = 1'b0;
    logic start_i = 1'b0;
    logic [3:0] rounds_i = '0;
    logic [319:0] state_i = '0;
    logic [319:0] state_o;
    logic busy_o;
    logic done_o;

    ascon_permutation dut (
        .clk(clk), .rst_n(rst_n), .start_i(start_i),
        .rounds_i(rounds_i), .state_i(state_i),
        .state_o(state_o), .busy_o(busy_o), .done_o(done_o)
    );

    string vectors_path;
    integer fd, parsed, count, cycles;
    integer rounds;
    logic [63:0] a0, a1, a2, a3, a4;
    logic [63:0] e0, e1, e2, e3, e4;
    logic [319:0] expected;

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
            parsed = $fscanf(fd,
                "%d %h %h %h %h %h %h %h %h %h %h\n",
                rounds, a0, a1, a2, a3, a4,
                e0, e1, e2, e3, e4);

            if (parsed == -1)
                break;
            if (parsed != 11)
                $fatal(1, "Malformed vector %0d: parsed %0d fields", count, parsed);

            expected = {e0, e1, e2, e3, e4};

            @(negedge clk);
            state_i  = {a0, a1, a2, a3, a4};
            rounds_i = rounds[3:0];
            start_i  = 1'b1;

            @(negedge clk);
            start_i = 1'b0;
            if (busy_o !== 1'b1)
                $fatal(1, "Controller did not start vector %0d", count);

            cycles = 0;
            while ((done_o !== 1'b1) && (cycles < rounds + 2)) begin
                @(posedge clk);
                #1;
                cycles++;
            end

            if (done_o !== 1'b1)
                $fatal(1, "Timeout on vector %0d", count);
            if (cycles != rounds)
                $fatal(1, "Latency mismatch on vector %0d: got %0d expected %0d", count, cycles, rounds);
            if (state_o !== expected)
                $fatal(1, "RTL mismatch on vector %0d: got %h expected %h", count, state_o, expected);

            @(posedge clk);
            #1;
            if (done_o !== 1'b0)
                $fatal(1, "done_o was not a one-cycle pulse on vector %0d", count);
            count++;
        end

        $fclose(fd);
        $display("PASS: %0d RTL permutations matched Python golden vectors", count);
        $finish;
    end
endmodule
