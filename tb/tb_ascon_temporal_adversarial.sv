`timescale 1ns/1ps
// Phase 7A permutation-level adversarial testbench.
// All expected outcomes are generated independently by Python before Verilator.
module tb_ascon_temporal_adversarial;
    logic clk = 1'b0;
    always #5 clk = ~clk;
    logic rst_n = 1'b0;
    logic start_i = 1'b0;
    logic [3:0] rounds_i = '0;
    logic [319:0] state_i = '0;
    logic first_arm_i = 1'b0, replay_arm_i = 1'b0;
    logic [3:0] first_round_i = '0, replay_round_i = '0;
    logic [8:0] first_bit_i = '0, replay_bit_i = '0;
    logic [1:0] checkpoint_mode_i = '0;
    logic [8:0] checkpoint_bit_i = '0;
    logic suppress_alarm_i = 1'b0;
    logic first_fired, replay_fired, checkpoint_fired, raw_mismatch;
    logic fault_detected, result_valid, busy, done;
    logic [319:0] result_state;

    ascon_permutation_adversarial dut (
        .clk(clk), .rst_n(rst_n), .start_i(start_i),
        .rounds_i(rounds_i), .state_i(state_i),
        .first_arm_i(first_arm_i), .first_round_i(first_round_i),
        .first_bit_i(first_bit_i), .replay_arm_i(replay_arm_i),
        .replay_round_i(replay_round_i), .replay_bit_i(replay_bit_i),
        .checkpoint_mode_i(checkpoint_mode_i),
        .checkpoint_bit_i(checkpoint_bit_i),
        .suppress_alarm_i(suppress_alarm_i),
        .first_fired_o(first_fired), .replay_fired_o(replay_fired),
        .checkpoint_fired_o(checkpoint_fired), .raw_mismatch_o(raw_mismatch),
        .fault_detected_o(fault_detected), .result_valid_o(result_valid),
        .state_o(result_state), .busy_o(busy), .done_o(done)
    );

    string vector_path;
    integer fd, parsed, count, cycles;
    integer i_rounds, i_first_arm, i_first_round, i_first_bit;
    integer i_replay_arm, i_replay_round, i_replay_bit;
    integer i_checkpoint_mode, i_checkpoint_bit, i_suppress_alarm;
    integer e_first_hit, e_replay_hit, e_cp_hit, e_mismatch, e_alarm, e_valid, e_silent;
    logic [319:0] i_state, golden, expected_output;

    initial begin
        if (!$value$plusargs("VECTORS=%s", vector_path))
            $fatal(1, "Missing +VECTORS=<path>");
        fd = $fopen(vector_path, "r");
        if (fd == 0) $fatal(1, "Cannot open vectors %s", vector_path);
        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        count = 0;
        while (!$feof(fd)) begin
            parsed = $fscanf(fd,
                "%d %h %d %d %d %d %d %d %d %d %d %h %d %d %d %d %d %d %h %d\n",
                i_rounds, i_state,
                i_first_arm, i_first_round, i_first_bit,
                i_replay_arm, i_replay_round, i_replay_bit,
                i_checkpoint_mode, i_checkpoint_bit, i_suppress_alarm,
                golden, e_first_hit, e_replay_hit, e_cp_hit,
                e_mismatch, e_alarm, e_valid, expected_output, e_silent);
            if (parsed == -1) break;
            if (parsed != 20)
                $fatal(1, "Bad vector %0d: read %0d fields", count, parsed);
            if (i_rounds != 8 && i_rounds != 12)
                $fatal(1, "Unexpected rounds %0d", i_rounds);

            @(negedge clk);
            state_i = i_state;
            rounds_i = i_rounds[3:0];
            first_arm_i = (i_first_arm != 0);
            first_round_i = i_first_round[3:0];
            first_bit_i = i_first_bit[8:0];
            replay_arm_i = (i_replay_arm != 0);
            replay_round_i = i_replay_round[3:0];
            replay_bit_i = i_replay_bit[8:0];
            checkpoint_mode_i = i_checkpoint_mode[1:0];
            checkpoint_bit_i = i_checkpoint_bit[8:0];
            suppress_alarm_i = (i_suppress_alarm != 0);
            start_i = 1'b1;
            @(negedge clk);
            start_i = 1'b0;
            if (busy !== 1'b1 || result_valid !== 1'b0 || result_state !== 320'd0)
                $fatal(1, "Invalid start / premature output case %0d", count);
            cycles = 0;
            while (done !== 1'b1 && cycles < 90) begin
                @(posedge clk); #1;
                cycles++;
                if (done !== 1'b1 && (result_valid !== 1'b0 || result_state !== 320'd0))
                    $fatal(1, "Premature output case %0d", count);
            end
            if (done !== 1'b1 || busy !== 1'b0)
                $fatal(1, "Timeout case %0d", count);
            if (first_fired !== (e_first_hit != 0) ||
                replay_fired !== (e_replay_hit != 0) ||
                checkpoint_fired !== (e_cp_hit != 0) ||
                raw_mismatch !== (e_mismatch != 0) ||
                fault_detected !== (e_alarm != 0) ||
                result_valid !== (e_valid != 0) ||
                result_state !== expected_output)
                $fatal(1, "Case %0d mismatch: first %b/%0d replay %b/%0d cp %b/%0d raw %b/%0d alarm %b/%0d valid %b/%0d state %h/%h",
                    count, first_fired, e_first_hit, replay_fired, e_replay_hit,
                    checkpoint_fired, e_cp_hit, raw_mismatch, e_mismatch,
                    fault_detected, e_alarm, result_valid, e_valid,
                    result_state, expected_output);
            if (((result_valid === 1'b1) && (result_state != golden)) !== (e_silent != 0))
                $fatal(1, "Wrong silent-corruption classification case %0d", count);
            if (!result_valid && (result_state !== 320'd0))
                $fatal(1, "Failure to fail closed case %0d", count);
            // Emit only observed RTL values, not just expectations.
            $display("RESULT %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
                count, i_rounds, first_fired, replay_fired,
                checkpoint_fired, raw_mismatch, fault_detected,
                result_valid, ((result_valid === 1'b1) && (result_state != golden)), cycles);
            @(posedge clk); #1;
            if (done !== 1'b0) $fatal(1, "DONE pulse too long case %0d", count);
            count++;
        end
        $fclose(fd);
        $display("PASS: %0d adversarial temporal permutations", count);
        $finish;
    end
endmodule
