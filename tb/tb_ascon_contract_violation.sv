`timescale 1ns/1ps
// Negative test: ensure --assert enables the monitor and detects a deliberate leak.
module tb_ascon_contract_violation;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0;
    logic [127:0] ciphertext_o = 0;
    ascon_temporal_safety_contract contract (
        .clk(clk), .rst_n(rst_n), .fault_detected_o(1'b0),
        .result_valid_o(1'b0), .ciphertext_o(ciphertext_o), .tag_o(128'd0),
        .busy_o(1'b0), .done_o(1'b0)
    );
    initial begin
        repeat (2) @(negedge clk);
        rst_n = 1;
        ciphertext_o = 128'h01; // deliberate invalid output leak
        repeat (3) @(negedge clk);
        $fatal(1, "Negative case did not activate SVA");
    end
endmodule
