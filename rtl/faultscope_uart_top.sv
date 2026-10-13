// FaultScope-Ascon board-interface pilot (laboratory evaluation only).
// UART 8N1; 100 MHz/115200 baud => CLOCKS_PER_BIT=868.
// Unauthenticated, unencrypted transport: NEVER send production keys.
// RX frame: A5 CMD LEN PAYLOAD[len] CRC8; CRC poly 07, init 00,
// calculated over CMD, LEN, PAYLOAD (not SOF).
// TX frame: 5A STATUS LEN PAYLOAD[len] CRC8 over STATUS/LEN/PAYLOAD.
// Only one request and response at a time; host waits for reply.
// READ result payload: msg_len, flags (bit 0 valid, bit 1 alarm,
// bit 2 fault-applied), ciphertext[16] LSB byte first, tag[16] LSB first.
module faultscope_uart_top #(
    parameter integer CLOCKS_PER_BIT = 868
) (
    input  logic clk,
    input  logic rst_n,
    input  logic uart_rx_i,
    output logic uart_tx_o,
    output logic led_busy_o,
    output logic led_alarm_o
);
    localparam logic [7:0] RX_SOF = 8'hA5, TX_SOF = 8'h5A;
    localparam logic [7:0] SET_KEY = 8'h10, SET_NONCE = 8'h11;
    localparam logic [7:0] SET_AD = 8'h12, SET_MSG = 8'h13;
    localparam logic [7:0] SET_CONTROL = 8'h14, START = 8'h20;
    localparam logic [7:0] READ_RESULT = 8'h21, PING = 8'h22;
    localparam logic [7:0] OK = 8'h00, BAD_LENGTH = 8'h01;
    localparam logic [7:0] BAD_CRC = 8'h02, BUSY = 8'h03;
    localparam logic [7:0] NOT_READY = 8'h04, BAD_COMMAND = 8'h05;
    localparam logic [7:0] BAD_CONTROL = 8'h06;

    function automatic logic [7:0] crc8_byte(input logic [7:0] old_crc,
                                              input logic [7:0] data);
        logic [7:0] c;
        c = old_crc ^ data;
        for (int j=0;j<8;j++) begin
            if (c[7]) c = (c << 1) ^ 8'h07;
            else c = c << 1;
        end
        return c;
    endfunction

    logic [7:0] rx_data, tx_data;
    logic rx_valid, tx_start_q, tx_busy;
    fs_uart_rx #(.CLOCKS_PER_BIT(CLOCKS_PER_BIT)) receiver (
        .clk(clk), .rst_n(rst_n), .rx_i(uart_rx_i),
        .data_o(rx_data), .valid_o(rx_valid));
    fs_uart_tx #(.CLOCKS_PER_BIT(CLOCKS_PER_BIT)) transmitter (
        .clk(clk), .rst_n(rst_n), .start_i(tx_start_q),
        .data_i(tx_data), .tx_o(uart_tx_o), .busy_o(tx_busy));

    logic [127:0] key_q, nonce_q, ad_q, msg_q;
    logic [4:0] ad_len_q, msg_len_q;
    logic fault_en_q;
    logic [2:0] fault_phase_q;
    logic [3:0] fault_round_q;
    logic [8:0] fault_bit_q;
    logic [4:0] loaded_q; // key, nonce, ad, msg, control

    logic core_start_q, core_applied, core_alarm, core_valid, core_busy, core_done;
    logic [127:0] core_ct, core_tag;
    logic pending_q, completed_q;
    assign led_busy_o = core_busy || pending_q;
    assign led_alarm_o = core_alarm;

    ascon_aead_encrypt_temporal core (
        .clk(clk), .rst_n(rst_n), .start_i(core_start_q),
        .key_i(key_q), .nonce_i(nonce_q),
        .associated_data_i(ad_q), .ad_len_i(ad_len_q),
        .plaintext_i(msg_q), .msg_len_i(msg_len_q),
        .fault_enable_i(fault_en_q), .fault_phase_i(fault_phase_q),
        .fault_round_i(fault_round_q), .fault_bit_i(fault_bit_q),
        .fault_applied_o(core_applied), .fault_detected_o(core_alarm),
        .result_valid_o(core_valid), .ciphertext_o(core_ct),
        .tag_o(core_tag), .busy_o(core_busy), .done_o(core_done));

    typedef enum logic [2:0] {R_SYNC, R_CMD, R_LEN, R_PAYLOAD, R_CRC} rx_state_t;
    rx_state_t rx_state_q;
    logic [7:0] command_q, length_q, crc_q;
    logic [4:0] rx_index_q;
    logic [7:0] request_payload [0:15];

    typedef enum logic [1:0] {T_IDLE, T_READY, T_WAIT_START, T_WAIT_END} tx_state_t;
    tx_state_t tx_state_q;
    logic [7:0] response_status_q, response_len_q, tx_index_q;
    logic [7:0] response_payload [0:33];
    logic [7:0] tx_crc_q;
    logic [7:0] next_tx_byte;

    always_comb begin
        next_tx_byte = '0;
        if (tx_index_q == 8'd0) next_tx_byte = TX_SOF;
        else if (tx_index_q == 8'd1) next_tx_byte = response_status_q;
        else if (tx_index_q == 8'd2) next_tx_byte = response_len_q;
        else if (tx_index_q == (response_len_q + 8'd3)) next_tx_byte = tx_crc_q;
        else if (tx_index_q >= 8'd3 && tx_index_q < (response_len_q + 8'd3))
            next_tx_byte = response_payload[tx_index_q - 8'd3];
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            key_q <= '0; nonce_q <= '0; ad_q <= '0; msg_q <= '0;
            ad_len_q <= '0; msg_len_q <= '0;
            fault_en_q <= 0; fault_phase_q <= 0; fault_round_q <= 0;
            fault_bit_q <= 0; loaded_q <= '0;
            core_start_q <= 0; pending_q <= 0; completed_q <= 0;
            command_q <= 0; length_q <= 0; crc_q <= 0; rx_index_q <= 0;
            rx_state_q <= R_SYNC;
            response_status_q <= OK; response_len_q <= 0;
            tx_state_q <= T_IDLE; tx_index_q <= 0;
            tx_start_q <= 0; tx_data <= 0; tx_crc_q <= 0;
            for (int b=0;b<16;b++) request_payload[b] <= 0;
            for (int b=0;b<34;b++) response_payload[b] <= 0;
        end else begin
            core_start_q <= 0;
            tx_start_q <= 0;
            if (core_done) begin
                completed_q <= 1;
                pending_q <= 0;
            end

            // Half-duplex protocol: host must not send another request while
            // a response is being transmitted. UART RX is discarded then.
            if (rx_valid && tx_state_q == T_IDLE) begin
                case (rx_state_q)
                    R_SYNC: if (rx_data == RX_SOF) rx_state_q <= R_CMD;
                    R_CMD: begin
                        command_q <= rx_data;
                        crc_q <= crc8_byte(8'h00, rx_data);
                        rx_state_q <= R_LEN;
                    end
                    R_LEN: begin
                        length_q <= rx_data;
                        crc_q <= crc8_byte(crc_q, rx_data);
                        rx_index_q <= 0;
                        if (rx_data > 8'd16) begin
                            response_status_q <= BAD_LENGTH;
                            response_len_q <= 0;
                            tx_index_q <= 0;
                            tx_state_q <= T_READY;
                            rx_state_q <= R_SYNC;
                        end else if (rx_data == 0) rx_state_q <= R_CRC;
                        else rx_state_q <= R_PAYLOAD;
                    end
                    R_PAYLOAD: begin
                        request_payload[rx_index_q] <= rx_data;
                        crc_q <= crc8_byte(crc_q, rx_data);
                        if (rx_index_q + 1 == length_q) rx_state_q <= R_CRC;
                        else rx_index_q <= rx_index_q + 1'b1;
                    end
                    R_CRC: begin
                        response_status_q <= OK;
                        response_len_q <= 0;
                        tx_index_q <= 0;
                        tx_state_q <= T_READY;
                        rx_state_q <= R_SYNC;
                        if (rx_data != crc_q) response_status_q <= BAD_CRC;
                        else if (core_busy || pending_q) begin
                            // READ returns BUSY; all modifications are denied.
                            response_status_q <= BUSY;
                        end else begin
                            case (command_q)
                                SET_KEY, SET_NONCE, SET_AD, SET_MSG: begin
                                    if (length_q != 8'd16) response_status_q <= BAD_LENGTH;
                                    else begin
                                        for (int b=0;b<16;b++) begin
                                            case (command_q)
                                                SET_KEY: key_q[8*b +:8] <= request_payload[b];
                                                SET_NONCE: nonce_q[8*b +:8] <= request_payload[b];
                                                SET_AD: ad_q[8*b +:8] <= request_payload[b];
                                                SET_MSG: msg_q[8*b +:8] <= request_payload[b];
                                                default: ;
                                            endcase
                                        end
                                        case (command_q)
                                            SET_KEY: loaded_q[0] <= 1;
                                            SET_NONCE: loaded_q[1] <= 1;
                                            SET_AD: loaded_q[2] <= 1;
                                            SET_MSG: loaded_q[3] <= 1;
                                            default: ;
                                        endcase
                                        completed_q <= 0;
                                    end
                                end
                                SET_CONTROL: begin
                                    if (length_q != 8'd7) response_status_q <= BAD_LENGTH;
                                    else if (request_payload[0] > 16 || request_payload[1] > 16 ||
                                             request_payload[2] > 1 || request_payload[3] > 4 ||
                                             request_payload[4] > 11 || request_payload[6] > 1 ||
                                             {request_payload[6][0], request_payload[5]} >= 9'd320)
                                        response_status_q <= BAD_CONTROL;
                                    else begin
                                        ad_len_q <= request_payload[0][4:0];
                                        msg_len_q <= request_payload[1][4:0];
                                        fault_en_q <= request_payload[2][0];
                                        fault_phase_q <= request_payload[3][2:0];
                                        fault_round_q <= request_payload[4][3:0];
                                        fault_bit_q <= {request_payload[6][0],request_payload[5]};
                                        loaded_q[4] <= 1;
                                        completed_q <= 0;
                                    end
                                end
                                START: begin
                                    if (length_q != 0) response_status_q <= BAD_LENGTH;
                                    else if (loaded_q != 5'b11111) response_status_q <= NOT_READY;
                                    else begin
                                        core_start_q <= 1;
                                        pending_q <= 1;
                                        completed_q <= 0;
                                    end
                                end
                                READ_RESULT: begin
                                    if (length_q != 0) response_status_q <= BAD_LENGTH;
                                    else if (!completed_q) response_status_q <= NOT_READY;
                                    else begin
                                        response_len_q <= 8'd34;
                                        response_payload[0] <= {3'b000,msg_len_q};
                                        response_payload[1] <= {5'b0,core_applied,core_alarm,core_valid};
                                        for (int b=0;b<16;b++) begin
                                            response_payload[b+2] <= core_ct[8*b +: 8];
                                            response_payload[b+18] <= core_tag[8*b +: 8];
                                        end
                                    end
                                end
                                PING: begin
                                    if (length_q != 0) response_status_q <= BAD_LENGTH;
                                    else begin
                                        response_len_q <= 2;
                                        response_payload[0] <= 8'h11;
                                        response_payload[1] <= 8'h00;
                                    end
                                end
                                default: response_status_q <= BAD_COMMAND;
                            endcase
                        end
                    end
                    default: rx_state_q <= R_SYNC;
                endcase
            end

            case (tx_state_q)
                T_IDLE: ;
                T_READY: if (!tx_busy) begin
                    tx_data <= next_tx_byte;
                    tx_start_q <= 1;
                    // Accumulate response CRC a byte at a time while the UART
                    // sends previous bytes; avoids a 34-byte combinational cone.
                    if (tx_index_q == 8'd0) tx_crc_q <= 0;
                    else if (tx_index_q < (response_len_q + 8'd3))
                        tx_crc_q <= crc8_byte(tx_crc_q, next_tx_byte);
                    tx_state_q <= T_WAIT_START;
                end
                T_WAIT_START: if (tx_busy) tx_state_q <= T_WAIT_END;
                T_WAIT_END: if (!tx_busy) begin
                    if (tx_index_q == (response_len_q + 8'd3)) tx_state_q <= T_IDLE;
                    else begin
                        tx_index_q <= tx_index_q + 1'b1;
                        tx_state_q <= T_READY;
                    end
                end
                default: tx_state_q <= T_IDLE;
            endcase
        end
    end
endmodule
