// Phase 13: asynchronously assert the reset, synchronously release it.
// This is NOT a debounce circuit, power-on-reset generator or CDC proof.
// The clock must run continuously during release. rst_n_async must satisfy
// the FPGA's minimum asynchronous reset pulse width.
module fs_reset_sync (
    input  logic clk,
    input  logic rst_n_async,
    output logic rst_n_sync
);
    // Avoid inferred shift-register LUTs and keep release stages together.
    (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) logic [2:0] release_pipe_q;

    always_ff @(posedge clk or negedge rst_n_async) begin
        if (!rst_n_async)
            release_pipe_q <= 3'b000;
        else
            release_pipe_q <= {release_pipe_q[1:0], 1'b1};
    end

    // Asynchronous assertion reaches consumers even without clock edges.
    // Deassertion takes 3 rising clock edges; consumers run next clock.
    assign rst_n_sync = release_pipe_q[2];
endmodule
