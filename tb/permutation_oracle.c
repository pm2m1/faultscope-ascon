
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include "permutations.h"

int main(void) {
    unsigned rounds;
    ascon_state_t state;

    while (scanf(
        "%u %" SCNx64 " %" SCNx64 " %" SCNx64
        " %" SCNx64 " %" SCNx64,
        &rounds,
        &state.x[0], &state.x[1], &state.x[2],
        &state.x[3], &state.x[4]
    ) == 6) {
        if (rounds == 12) {
            P12(&state);
        } else if (rounds == 8) {
            P8(&state);
        } else {
            return 1;
        }

        for (int i = 0; i < 5; ++i) {
            printf("%016" PRIx64 "%c",
                   state.x[i], i == 4 ? '\n' : ' ');
        }
    }

    return 0;
}
