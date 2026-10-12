// Ascon one-round combinational datapath, NIST SP 800-232.
// State lane packing: {x0, x1, x2, x3, x4}, each lane 64 bits.
// Round constants are XORed into the least significant bits of x2.
module ascon_round (
    input  logic [319:0] state_i,
    input  logic [7:0]   round_constant_i,
    output logic [319:0] state_o
);
    logic [63:0] x0, x1, x2, x3, x4;
    logic [63:0] t0, t1, t2, t3, t4;

    function automatic logic [63:0] ror64(
        input logic [63:0] value,
        input integer unsigned shift
    );
        return (value >> shift) | (value << (64 - shift));
    endfunction

    always_comb begin
        {x0, x1, x2, x3, x4} = state_i;

        // Add round constant.
        x2 = x2 ^ {56'b0, round_constant_i};

        // 5-bit bitsliced nonlinear substitution (64 parallel S-boxes).
        x0 = x0 ^ x4;
        x4 = x4 ^ x3;
        x2 = x2 ^ x1;

        t0 = x0 ^ (~x1 & x2);
        t1 = x1 ^ (~x2 & x3);
        t2 = x2 ^ (~x3 & x4);
        t3 = x3 ^ (~x4 & x0);
        t4 = x4 ^ (~x0 & x1);

        t1 = t1 ^ t0;
        t0 = t0 ^ t4;
        t3 = t3 ^ t2;
        t2 = ~t2;

        // Linear diffusion, lane-specific rotations.
        state_o = {
            t0 ^ ror64(t0, 19) ^ ror64(t0, 28),
            t1 ^ ror64(t1, 61) ^ ror64(t1, 39),
            t2 ^ ror64(t2,  1) ^ ror64(t2,  6),
            t3 ^ ror64(t3, 10) ^ ror64(t3, 17),
            t4 ^ ror64(t4,  7) ^ ror64(t4, 41)
        };
    end
endmodule
