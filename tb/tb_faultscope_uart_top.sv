`timescale 1ns/1ps
// Actual UART bit-level transaction tests against unchanged temporal Ascon RTL.
module tb_faultscope_uart_top;
    localparam integer CPB = 8; // Simulation-only clock/bit ratio.
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, uart_rx = 1;
    logic uart_tx, led_busy, led_alarm;
    faultscope_uart_top #(.CLOCKS_PER_BIT(CPB)) dut (
        .clk(clk), .rst_n(rst_n), .uart_rx_i(uart_rx),
        .uart_tx_o(uart_tx), .led_busy_o(led_busy), .led_alarm_o(led_alarm));

    logic [7:0] host_payload [0:15];
    logic [7:0] response_bytes [0:33];
    logic [7:0] last_status;
    integer last_length;

    function automatic logic [7:0] crc8_byte(input logic [7:0] old_crc,
                                              input logic [7:0] data);
        logic [7:0] c;
        c = old_crc ^ data;
        for (integer i=0;i<8;i++) begin
            if (c[7]) c = (c << 1) ^ 8'h07;
            else c = c << 1;
        end
        return c;
    endfunction

    task automatic uart_write_byte(input logic [7:0] byte_value);
        @(negedge clk);
        uart_rx = 0;
        repeat(CPB) @(negedge clk);
        for (integer b=0;b<8;b++) begin
            uart_rx = byte_value[b];
            repeat(CPB) @(negedge clk);
        end
        uart_rx = 1;
        repeat(CPB) @(negedge clk);
    endtask

    task automatic uart_read_byte(output logic [7:0] byte_value);
        byte_value = 0;
        @(negedge uart_tx);
        repeat(CPB + CPB/2) @(posedge clk);
        for (integer b=0;b<8;b++) begin
            byte_value[b] = uart_tx;
            repeat(CPB) @(posedge clk);
        end
        if (uart_tx !== 1'b1) $fatal(1, "UART stop bit not high");
    endtask

    // Producer and consumer fork so no transmit bytes are lost while sending.
    task automatic exchange(input logic [7:0] cmd, input integer len,
                            input bit corrupt_crc);
        logic [7:0] send_crc, receive_crc;
        logic [7:0] b;
        integer payload_count;
        fork
            begin : host_send
                send_crc = crc8_byte(crc8_byte(0,cmd),len[7:0]);
                uart_write_byte(8'hA5);
                uart_write_byte(cmd);
                uart_write_byte(len[7:0]);
                for (integer i=0;i<len;i++) begin
                    uart_write_byte(host_payload[i]);
                    send_crc = crc8_byte(send_crc,host_payload[i]);
                end
                uart_write_byte(corrupt_crc ? (send_crc ^ 8'h01) : send_crc);
            end
            begin : host_receive
                uart_read_byte(b);
                if (b != 8'h5A) $fatal(1, "Incorrect response SOF %02x",b);
                uart_read_byte(last_status);
                uart_read_byte(b);
                last_length = b;
                if (last_length > 34) $fatal(1, "Invalid returned length %d",last_length);
                payload_count = last_length;
                for (integer i=0;i<payload_count;i++) uart_read_byte(response_bytes[i]);
                uart_read_byte(b);
                receive_crc = crc8_byte(crc8_byte(0,last_status),payload_count[7:0]);
                for (integer i=0;i<payload_count;i++)
                    receive_crc = crc8_byte(receive_crc,response_bytes[i]);
                if (b !== receive_crc) $fatal(1, "Response CRC mismatch %02x vs %02x",b,receive_crc);
            end
        join
        if (last_status != 0 && last_length != 0)
            $fatal(1, "Nonzero-status response must not include payload");
    endtask

    task automatic expect_status(input logic [7:0] cmd,input integer len,
                                 input bit corrupt, input logic [7:0] status);
        exchange(cmd,len,corrupt);
        if (last_status !== status) $fatal(1,"Bad response cmd=%02x status=%02x expected=%02x", cmd,last_status,status);
    endtask

    task automatic wait_result();
        bit done;
        done=0;
        for (integer k=0;k<20;k++) begin
            exchange(8'h21,0,0);
            if (last_status == 8'h00) begin
                if (last_length != 34) $fatal(1,"Result length wrong");
                done=1;
                break;
            end
            if (last_status != 8'h03 && last_status != 8'h04)
                $fatal(1,"Unexpected read status %02x",last_status);
        end
        if (!done) $fatal(1,"No completed transaction after polling");
    endtask

    initial begin
        repeat(5) @(negedge clk);
        rst_n=1;
        for (integer b=0;b<16;b++) host_payload[b]=0;
        expect_status(8'h22,0,0,8'h00);
        if (last_length != 2 || response_bytes[0] != 8'h11 || response_bytes[1] != 0)
            $fatal(1,"PING version incorrect");
        expect_status(8'h21,0,0,8'h04); // READ before any transaction
        expect_status(8'h22,0,1,8'h02); // Deliberately bad CRC
        for (integer b=0;b<16;b++) host_payload[b]=b[7:0];
        expect_status(8'h10,16,0,8'h00);
        for (integer b=0;b<16;b++) host_payload[b]=(b+16);
        expect_status(8'h11,16,0,8'h00);
        for (integer b=0;b<16;b++) host_payload[b]=0;
        expect_status(8'h12,16,0,8'h00);
        expect_status(8'h13,16,0,8'h00);
        host_payload[0]=17;
        host_payload[1]=0; host_payload[2]=0;
        host_payload[3]=0; host_payload[4]=0;
        host_payload[5]=0; host_payload[6]=0;
        expect_status(8'h14,7,0,8'h06); // Reject AD length > 16
        host_payload[0]=0;
        expect_status(8'h14,7,0,8'h00);
        expect_status(8'h20,0,0,8'h00);
        wait_result();
        if (response_bytes[0] !== 0 || response_bytes[1] !== 8'h01)
            $fatal(1,"Clean valid flag not returned");
        for (integer b=0;b<16;b++)
            if (response_bytes[2+b] !== 0) $fatal(1,"Expected empty ciphertext");
        // Officially checked Python Ascon reference result for k=00..0f,
        // nonce=10..1f, AD=empty, plaintext=empty.
        begin : check_known_tag
            logic [127:0] known_tag;
            known_tag=128'hc62e8bee468ff66b31c9be1182279c4f;
            for (integer b=0;b<16;b++)
                if (response_bytes[18+b] !== known_tag[8*b+:8])
                    $fatal(1,"Known tag mismatch byte %0d got %02x",b,response_bytes[18+b]);
        end
        // Reconfigure to fault at phase 0 / first round / bit 0.
        host_payload[0]=0; host_payload[1]=0; host_payload[2]=1;
        host_payload[3]=0; host_payload[4]=0;
        host_payload[5]=0; host_payload[6]=0;
        expect_status(8'h14,7,0,8'h00);
        expect_status(8'h20,0,0,8'h00);
        wait_result();
        if (response_bytes[1] !== 8'h06) $fatal(1,"Fault flags expected fired+alarm no valid");
        for (integer b=0;b<32;b++)
            if (response_bytes[2+b] !== 0) $fatal(1,"Fault released ciphertext/tag");
        if (led_alarm !== 1) $fatal(1,"Alarm LED not asserted");
        $display("PASS: UART protected AEAD clean tag, fault alarm, invalid CRC");
        $finish;
    end
    initial begin
        #3000000; // Safety timeout (300k 100 MHz cycles)
        $fatal(1,"UART bench timed out");
    end
endmodule
