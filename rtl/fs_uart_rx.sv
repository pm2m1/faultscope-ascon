// Educational 8N1 UART receiver: two-flop input synchronizer, LSB first.
// CLOCKS_PER_BIT must be >= 8. No parity, framing-error count, or FIFO.
module fs_uart_rx #(
    parameter integer CLOCKS_PER_BIT = 868
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       rx_i,
    output logic [7:0] data_o,
    output logic       valid_o
);
    typedef enum logic [1:0] {WAIT_START, CHECK_START, RECEIVE, CHECK_STOP} state_t;
    state_t state_q;
    logic [1:0] sync_q;
    logic [31:0] ticks_q;
    logic [2:0] bit_q;
    logic [7:0] shift_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sync_q <= 2'b11;
            ticks_q <= '0;
            bit_q <= '0;
            shift_q <= '0;
            data_o <= '0;
            valid_o <= 1'b0;
            state_q <= WAIT_START;
        end else begin
            sync_q <= {sync_q[0], rx_i};
            valid_o <= 1'b0;
            case (state_q)
                WAIT_START: if (!sync_q[1]) begin
                    ticks_q <= (CLOCKS_PER_BIT / 2) - 1;
                    state_q <= CHECK_START;
                end
                CHECK_START: if (ticks_q != 0) ticks_q <= ticks_q - 1;
                             else if (!sync_q[1]) begin
                                 ticks_q <= CLOCKS_PER_BIT - 1;
                                 bit_q <= '0;
                                 state_q <= RECEIVE;
                             end else state_q <= WAIT_START;
                RECEIVE: if (ticks_q != 0) ticks_q <= ticks_q - 1;
                         else begin
                             shift_q[bit_q] <= sync_q[1];
                             ticks_q <= CLOCKS_PER_BIT - 1;
                             if (bit_q == 3'd7) state_q <= CHECK_STOP;
                             else bit_q <= bit_q + 1'b1;
                         end
                CHECK_STOP: if (ticks_q != 0) ticks_q <= ticks_q - 1;
                            else begin
                                if (sync_q[1]) begin
                                    data_o <= shift_q;
                                    valid_o <= 1'b1;
                                end
                                state_q <= WAIT_START;
                            end
                default: state_q <= WAIT_START;
            endcase
        end
    end
endmodule
