// Educational 8N1 UART sender: one-byte handshake, LSB first, idle high.
module fs_uart_tx #(
    parameter integer CLOCKS_PER_BIT = 868
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       start_i,
    input  logic [7:0] data_i,
    output logic       tx_o,
    output logic       busy_o
);
    typedef enum logic [1:0] {READY, START_BIT, SEND_DATA, STOP_BIT} state_t;
    state_t state_q;
    logic [31:0] ticks_q;
    logic [2:0] bit_q;
    logic [7:0] shift_q;

    assign busy_o = (state_q != READY);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q <= READY;
            ticks_q <= '0;
            bit_q <= '0;
            shift_q <= '0;
            tx_o <= 1'b1;
        end else begin
            case (state_q)
                READY: if (start_i) begin
                    shift_q <= data_i;
                    tx_o <= 1'b0;
                    ticks_q <= CLOCKS_PER_BIT - 1;
                    state_q <= START_BIT;
                end
                START_BIT: if (ticks_q != 0) ticks_q <= ticks_q - 1;
                           else begin
                               tx_o <= shift_q[0];
                               ticks_q <= CLOCKS_PER_BIT - 1;
                               bit_q <= '0;
                               state_q <= SEND_DATA;
                           end
                SEND_DATA: if (ticks_q != 0) ticks_q <= ticks_q - 1;
                           else if (bit_q == 3'd7) begin
                               tx_o <= 1'b1;
                               ticks_q <= CLOCKS_PER_BIT - 1;
                               state_q <= STOP_BIT;
                           end else begin
                               bit_q <= bit_q + 1'b1;
                               tx_o <= shift_q[bit_q + 1'b1];
                               ticks_q <= CLOCKS_PER_BIT - 1;
                           end
                STOP_BIT: if (ticks_q != 0) ticks_q <= ticks_q - 1;
                          else state_q <= READY;
                default: state_q <= READY;
            endcase
        end
    end
endmodule
