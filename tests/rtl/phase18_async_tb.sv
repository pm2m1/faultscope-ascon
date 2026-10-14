// Phase 18 behavioral RTL regression only (no analog metastability or real board model).
// Compile original rtl/fs_reset_sync.sv and rtl/fs_uart_rx.sv unchanged.
`timescale 1ns/1ps
module phase18_async_tb;
    localparam int CPB = 16;
    logic clk = 1'b0;
    logic rst_n_async = 1'b0;
    logic uart_rx = 1'b1;
    wire rst_n_core;
    wire [7:0] rx_data;
    wire rx_valid;
    int accepted = 0;
    logic [7:0] last_data = 0;
    always #5 clk = ~clk;

    fs_reset_sync u_reset_sync (
        .clk(clk), .rst_n_async(rst_n_async), .rst_n_sync(rst_n_core)
    );
    fs_uart_rx #(.CLOCKS_PER_BIT(CPB)) receiver (
        .clk(clk), .rst_n(rst_n_core), .rx_i(uart_rx),
        .data_o(rx_data), .valid_o(rx_valid)
    );

    always @(posedge clk) begin
        #1;
        if (rx_valid) begin
            accepted = accepted + 1;
            last_data = rx_data;
        end
    end

    task automatic wait_cycles(input int n);
        repeat (n) @(negedge clk);
    endtask

    task automatic release_check();
        @(negedge clk);
        rst_n_async = 1'b1;
        @(posedge clk); #1;
        if (rst_n_core !== 1'b0) $fatal(1, "Reset released before stage 3 (cycle 1)");
        @(posedge clk); #1;
        if (rst_n_core !== 1'b0) $fatal(1, "Reset released before stage 3 (cycle 2)");
        @(posedge clk); #1;
        if (rst_n_core !== 1'b1) $fatal(1, "Reset did not release on third clock");
    endtask

    task automatic send_bit(input logic bit_value);
        @(negedge clk);
        uart_rx = bit_value;
        wait_cycles(CPB-1);
    endtask

    task automatic send_byte(input logic [7:0] value);
        send_bit(1'b0);
        for (int i=0; i<8; i++) send_bit(value[i]);
        send_bit(1'b1);
        @(negedge clk);
        uart_rx = 1'b1;
    endtask

    initial begin
        // Known low reset asserted before first rising edge.
        #2;
        if (rst_n_core !== 1'b0) $fatal(1, "Reset not asserted at startup");
        release_check();
        wait_cycles(8);

        // Off-clock assertion must propagate WITHOUT waiting for a rising edge.
        #2 rst_n_async = 1'b0;
        #1;
        if (rst_n_core !== 1'b0) $fatal(1, "Reset failed asynchronous assertion");
        release_check();
        wait_cycles(8);

        // Short UART start-like glitch (< half a bit) must be rejected.
        @(negedge clk) uart_rx = 1'b0;
        wait_cycles(2);
        uart_rx = 1'b1;
        wait_cycles(CPB*3);
        if (accepted != 0) $fatal(1, "Glitch caused received byte");

        // Valid 8N1 byte must pass through original two-flop RX chain.
        send_byte(8'hA6);
        wait_cycles(CPB*3);
        if (accepted != 1 || last_data !== 8'hA6)
            $fatal(1, "Valid UART byte not accepted correctly (count=%0d data=%h)",accepted,last_data);

        // Reset during a low start pulse must clear receiver state.
        @(negedge clk) uart_rx = 1'b0;
        wait_cycles(CPB/2);
        #2 rst_n_async = 1'b0;
        #1;
        if (rst_n_core !== 1'b0) $fatal(1, "Mid-frame reset assertion not immediate");
        uart_rx = 1'b1;
        wait_cycles(4);
        release_check();
        wait_cycles(CPB*3);
        if (accepted != 1) $fatal(1, "Stale partial UART frame accepted after reset");

        send_byte(8'h35);
        wait_cycles(CPB*3);
        if (accepted != 2 || last_data !== 8'h35)
            $fatal(1, "UART did not recover after reset (count=%0d data=%h)",accepted,last_data);

        $display("PHASE18_XSIM_PASS: reset assertion/release, glitch rejection, UART reception, reset interruption and recovery");
        $finish;
    end

    initial begin
        #30000;
        $fatal(1, "Phase 18 simulation timeout");
    end
endmodule
