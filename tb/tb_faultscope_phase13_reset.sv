`timescale 1ns/1ps
// Phase 13 reset-interruption checks on the real temporal-AEAD/UART hierarchy.
// The simulation uses a speed-up CLOCKS_PER_BIT; Vivado uses default 868.
module tb_faultscope_phase13_reset;
    localparam integer CPB = 8;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, uart_rx = 1;
    logic uart_tx, led_busy, led_alarm;

    faultscope_uart_top #(.CLOCKS_PER_BIT(CPB)) dut (
        .clk(clk), .rst_n(rst_n), .uart_rx_i(uart_rx),
        .uart_tx_o(uart_tx), .led_busy_o(led_busy), .led_alarm_o(led_alarm));

    logic [7:0] payload [0:15];
    logic [7:0] reply [0:33];
    logic [7:0] status;
    integer reply_length;

    function automatic logic [7:0] crc8_byte(input logic [7:0] start,
                                              input logic [7:0] data);
        logic [7:0] c;
        c = start ^ data;
        for (integer k=0; k<8; k++)
            c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
        return c;
    endfunction

    task automatic send_byte(input logic [7:0] data);
        @(negedge clk); uart_rx = 0;
        repeat (CPB) @(negedge clk);
        for (integer b=0; b<8; b++) begin
            uart_rx = data[b];
            repeat (CPB) @(negedge clk);
        end
        uart_rx = 1;
        repeat (CPB) @(negedge clk);
    endtask

    task automatic send_frame(input logic [7:0] command, input integer len);
        logic [7:0] crc;
        crc = crc8_byte(crc8_byte(8'h00, command), len[7:0]);
        send_byte(8'hA5);
        send_byte(command);
        send_byte(len[7:0]);
        for (integer k=0;k<len;k++) begin
            send_byte(payload[k]);
            crc = crc8_byte(crc, payload[k]);
        end
        send_byte(crc);
    endtask

    task automatic read_byte(output logic [7:0] data);
        data=0;
        @(negedge uart_tx);
        repeat (CPB+CPB/2) @(posedge clk);
        for (integer b=0; b<8; b++) begin
            data[b]=uart_tx;
            repeat (CPB) @(posedge clk);
        end
        if (uart_tx !== 1'b1) $fatal(1,"Bad UART stop bit");
    endtask

    task automatic exchange(input logic [7:0] command, input integer len);
        logic [7:0] item, crc;
        integer count;
        fork
            begin : send
                send_frame(command,len);
            end
            begin : receive
                read_byte(item);
                if (item !== 8'h5A) $fatal(1,"Missing UART response SOF");
                read_byte(status);
                read_byte(item);
                count = item;
                reply_length = count;
                if (count > 34) $fatal(1,"Oversize UART response");
                for (integer k=0;k<count;k++) read_byte(reply[k]);
                read_byte(item);
                crc=crc8_byte(crc8_byte(0,status),count[7:0]);
                for (integer k=0;k<count;k++) crc=crc8_byte(crc,reply[k]);
                if (item !== crc) $fatal(1,"Response CRC incorrect");
            end
        join
    endtask

    task automatic expect_status(input logic [7:0] cmd, input integer len,
                                 input logic [7:0] expected);
        exchange(cmd,len);
        if (status !== expected) $fatal(1,"Command %02x returned %02x not %02x",cmd,status,expected);
    endtask

    task automatic assert_held_reset();
        #1;
        if (dut.rst_n_core !== 1'b0 || uart_tx !== 1'b1 ||
            led_busy !== 1'b0 || led_alarm !== 1'b0)
            $fatal(1,"Asynchronous reset assertion did not suppress state/outputs");
    endtask

    task automatic release_after_offset(input integer offset_ns);
        // Begin low while clock runs; release between edges, not at an edge.
        rst_n=0; uart_rx=1;
        assert_held_reset();
        @(negedge clk); #(offset_ns); rst_n=1;
        #1;
        if (dut.rst_n_core !== 0) $fatal(1,"Reset deasserted asynchronously");
        for (integer edge_count=1;edge_count<=3;edge_count++) begin
            @(posedge clk); #1;
            if (dut.rst_n_core !== (edge_count==3))
                $fatal(1,"Wrong synchronous release at edge %0d",edge_count);
        end
        repeat (4) @(negedge clk);
    endtask

    task automatic configure_zero_message(input logic injected);
        for (integer b=0;b<16;b++) payload[b]=b[7:0];
        expect_status(8'h10,16,0);
        for (integer b=0;b<16;b++) payload[b]=8'(b+16);
        expect_status(8'h11,16,0);
        for (integer b=0;b<16;b++) payload[b]=0;
        expect_status(8'h12,16,0);
        expect_status(8'h13,16,0);
        payload[0]=0; payload[1]=0; payload[2]=injected;
        payload[3]=0; payload[4]=0; payload[5]=0; payload[6]=0;
        expect_status(8'h14,7,0);
    endtask

    task automatic wait_result();
        bit done;
        done=0;
        for (integer k=0;k<25;k++) begin
            exchange(8'h21,0);
            if (status==0) begin
                if (reply_length != 34) $fatal(1,"READ_RESULT length invalid");
                done=1;
                break;
            end
            if (status != 8'h03 && status != 8'h04)
                $fatal(1,"Unexpected result response %02x",status);
        end
        if (!done) $fatal(1,"READ_RESULT timed out");
    endtask

    initial begin
        for (integer b=0;b<16;b++) payload[b]=0;
        // Establish the released reset state in simulation before
        // testing a real asynchronous assertion.
        rst_n = 1'b1;
        uart_rx = 1'b1;
        repeat (6) @(negedge clk);
        if (dut.rst_n_core !== 1'b1)
            $fatal(1, "Reset synchronizer did not release");

        // Assert reset away from a clock edge.
        #2;
        rst_n = 1'b0;
        assert_held_reset();
        // Three asynchronous-release phases: 1, 2 and 3 ns from falling edge.
        release_after_offset(1);
        expect_status(8'h22,0,0);
        release_after_offset(2);
        expect_status(8'h21,0,8'h04);
        release_after_offset(3);
        expect_status(8'h20,0,8'h04);

        // Incomplete request: reset halfway through command byte.
        send_byte(8'hA5);
        @(negedge clk); uart_rx=0;
        repeat (4) @(negedge clk);
        rst_n=0; uart_rx=1;
        assert_held_reset();
        repeat (2) @(negedge clk);
        release_after_offset(2);
        expect_status(8'h22,0,0);
        expect_status(8'h21,0,8'h04);

        // Reset in the middle of an outgoing response byte. Do not attempt
        // to receive an incomplete response: UART is a resettable lab link.
        fork
            begin : trigger_reply
                send_frame(8'h22,0);
            end
            begin : kill_reply
                @(negedge uart_tx);
                repeat (3) @(negedge clk);
                rst_n=0;
                assert_held_reset();
                repeat (4) @(negedge clk);
                rst_n=1;
            end
        join
        repeat (8) @(negedge clk);
        expect_status(8'h22,0,0);

        // Reset during active Ascon computation, not after START response:
        // UART ack is slower than the protected core at CPB=8.
        configure_zero_message(0);
        fork
            begin : trigger_core
                send_frame(8'h20,0);
            end
            begin : kill_core
                wait (dut.core_busy === 1'b1);
                repeat (3) @(negedge clk);
                rst_n=0;
                assert_held_reset();
                repeat (4) @(negedge clk);
                rst_n=1;
            end
        join
        repeat (8) @(negedge clk);
        if (dut.loaded_q !== 0 || dut.completed_q !== 0 || dut.core_valid !== 0)
            $fatal(1,"Stale configuration/result survived reset during core");
        expect_status(8'h21,0,8'h04);
        expect_status(8'h20,0,8'h04);
        expect_status(8'h22,0,0);

        // Produce a REAL fault alarm and then reset it, not a forced signal.
        configure_zero_message(1);
        expect_status(8'h20,0,0);
        wait_result();
        if (reply[1] !== 8'h06 || led_alarm !== 1)
            $fatal(1,"Real injected fault must latch alarm with no valid result");
        for (integer b=0;b<32;b++)
            if (reply[2+b] !== 0) $fatal(1,"Faulted operation leaked data");
        @(negedge clk); #2; rst_n=0;
        assert_held_reset();
        repeat (3) @(negedge clk);
        release_after_offset(1);
        expect_status(8'h21,0,8'h04);
        expect_status(8'h20,0,8'h04);
        expect_status(8'h22,0,0);
        $display("PASS: Phase 13 reset release and UART/core/fault interruption");
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1,"Phase 13 reset bench timeout");
    end
endmodule
