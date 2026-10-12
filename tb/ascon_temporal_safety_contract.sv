// Simulation-checked SystemVerilog assertions for the actual protected RTL I/O.
// These are safety assertions, NOT an exhaustive formal proof of the controller.
// Check with Verilator --assert or integrate into a future formal harness.
module ascon_temporal_safety_contract (
    input logic clk,
    input logic rst_n,
    input logic fault_detected_o,
    input logic result_valid_o,
    input logic [127:0] ciphertext_o,
    input logic [127:0] tag_o,
    input logic busy_o,
    input logic done_o
);
    // Externally invalid results must never expose private interim datapath bytes.
    CONTRACT_OUTPUT_MASK: assert property (
        @(posedge clk) disable iff (!rst_n)
        !result_valid_o |-> (ciphertext_o == 128'd0 && tag_o == 128'd0)
    ) else $fatal(1, "CONTRACT_OUTPUT_MASK: invalid output exposed data");

    // A sticky alarm must inhibit externally valid ciphertext/tag release.
    CONTRACT_ALARM_BLOCKS_RELEASE: assert property (
        @(posedge clk) disable iff (!rst_n)
        fault_detected_o |-> (!result_valid_o && ciphertext_o == 128'd0 && tag_o == 128'd0)
    ) else $fatal(1, "CONTRACT_ALARM_BLOCKS_RELEASE: alarm failed closed");

    // No externally valid result while the transaction remains in progress.
    CONTRACT_NO_EARLY_RELEASE: assert property (
        @(posedge clk) disable iff (!rst_n)
        busy_o |-> (!result_valid_o && ciphertext_o == 128'd0 && tag_o == 128'd0)
    ) else $fatal(1, "CONTRACT_NO_EARLY_RELEASE: premature output");

    // Completion is a single-cycle pulse after the controller goes idle.
    CONTRACT_DONE_IDLE: assert property (
        @(posedge clk) disable iff (!rst_n)
        done_o |-> !busy_o
    ) else $fatal(1, "CONTRACT_DONE_IDLE: done while busy");

    CONTRACT_DONE_PULSE: assert property (
        @(posedge clk) disable iff (!rst_n)
        done_o |=> !done_o
    ) else $fatal(1, "CONTRACT_DONE_PULSE: done stuck high");
endmodule
