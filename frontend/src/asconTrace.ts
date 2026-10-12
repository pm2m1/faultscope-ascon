/** Educational Ascon p[8]/p[12] round trace, NIST SP 800-232 word conventions.
 * Pure deterministic functions; no encryption/key management or WebCrypto.
 * Verified independently against reference/ascon_permutation.py.
 */
export type FiveWords = readonly [bigint, bigint, bigint, bigint, bigint];
export type Stage = 'input' | 'constant' | 'substitution' | 'diffusion';
export type TraceFrame = {
  roundIndex: number; roundCount: 8 | 12; constant: number | null;
  stage: Stage; lanes: FiveWords; explanation: string;
};
export type ReplayScenario =
  'clean' | 'first_only' | 'replay_only' | 'dual_identical' |
  'checkpoint_shared' | 'checkpoint_replay' |
  'suppress_replay_alarm' | 'suppress_first_alarm';
export type ReplayAnalysis = {
  golden: FiveWords; first: FiveWords; replay: FiveWords;
  firstFired: boolean; replayFired: boolean; checkpointFired: boolean;
  rawMismatch: boolean; alarm: boolean; valid: boolean; incorrectRelease: boolean;
};
const MASK64 = (1n << 64n) - 1n;
const RC = [0xf0, 0xe1, 0xd2, 0xc3, 0xb4, 0xa5, 0x96, 0x87, 0x78, 0x69, 0x5a, 0x4b] as const;
const ROTATIONS = [[19, 28], [61, 39], [1, 6], [10, 17], [7, 41]] as const;
const m = (v: bigint) => v & MASK64;
const rotr = (v: bigint, k: number) => m((v >> BigInt(k)) | (v << BigInt(64 - k)));
export const hex64 = (v: bigint) => v.toString(16).padStart(16, '0');
export const wordsEqual = (a: FiveWords, b: FiveWords) => a.every((w, i) => w === b[i]);
export const zeros: FiveWords = [0n, 0n, 0n, 0n, 0n];
export const sequence: FiveWords = [1n, 2n, 3n, 4n, 5n];
export const allOnes: FiveWords = [MASK64, MASK64, MASK64, MASK64, MASK64];

export function parseLaneHex(text: string): bigint | null {
  const s = text.trim().replace(/^0x/i, '');
  if (!/^[0-9a-f]{1,16}$/i.test(s)) return null;
  return BigInt(`0x${s}`);
}

export function roundStages(state: FiveWords, constant: number): { constant: FiveWords; substitution: FiveWords; diffusion: FiveWords } {
  if (!Number.isInteger(constant) || constant < 0 || constant > 255) throw new Error('Bad round constant');
  const c: FiveWords = [state[0], state[1], m(state[2] ^ BigInt(constant)), state[3], state[4]];
  let [x0, x1, x2, x3, x4] = c;
  x0 = m(x0 ^ x4);
  x4 = m(x4 ^ x3);
  x2 = m(x2 ^ x1);
  let t0 = m(x0 ^ (~x1 & x2));
  let t1 = m(x1 ^ (~x2 & x3));
  let t2 = m(x2 ^ (~x3 & x4));
  let t3 = m(x3 ^ (~x4 & x0));
  let t4 = m(x4 ^ (~x0 & x1));
  t1 = m(t1 ^ t0);
  t0 = m(t0 ^ t4);
  t3 = m(t3 ^ t2);
  t2 = m(~t2);
  const substitution: FiveWords = [t0, t1, t2, t3, t4];
  const words = substitution.map((v, i) => m(v ^ rotr(v, ROTATIONS[i][0]) ^ rotr(v, ROTATIONS[i][1])));
  const diffusion = words as unknown as FiveWords;
  return { constant: c, substitution, diffusion };
}

export function asconTrace(initial: FiveWords, rounds: 8 | 12): TraceFrame[] {
  if (rounds !== 8 && rounds !== 12) throw new Error('Only p[8] and p[12] supported');
  if (initial.length !== 5 || initial.some(v => v < 0n || v > MASK64)) throw new Error('State must have five 64-bit words');
  const frames: TraceFrame[] = [{ roundIndex: -1, roundCount: rounds, constant: null,
    stage: 'input', lanes: initial, explanation: 'Starting 320-bit state: five 64-bit words x0–x4.' }];
  let state = initial;
  RC.slice(12 - rounds).forEach((constant, roundIndex) => {
    const step = roundStages(state, constant);
    const id = `${roundIndex + 1} of ${rounds}`;
    frames.push({ roundIndex, roundCount: rounds, constant, stage: 'constant', lanes: step.constant,
      explanation: `Round ${id}: XOR 0x${constant.toString(16).padStart(2, '0')} into x2 (the round constant).` });
    frames.push({ roundIndex, roundCount: rounds, constant, stage: 'substitution', lanes: step.substitution,
      explanation: `Round ${id}: apply the 5-bit nonlinear Ascon S-box in parallel across all 64 bit positions.` });
    frames.push({ roundIndex, roundCount: rounds, constant, stage: 'diffusion', lanes: step.diffusion,
      explanation: `Round ${id}: for each word x, compute x XOR ROTR(x,a) XOR ROTR(x,b).` });
    state = step.diffusion;
  });
  return frames;
}

export function flipStateBit(state: FiveWords, bit: number): FiveWords {
  if (!Number.isInteger(bit) || bit < 0 || bit >= 320) throw new Error('Bit index must be 0…319');
  const words = [...state];
  // RTL state_o={x0,x1,x2,x3,x4}: bit 0 is x4[0].
  const wordIndex = 4 - Math.floor(bit / 64);
  words[wordIndex] ^= 1n << BigInt(bit % 64);
  return words as unknown as FiveWords;
}

export function permute(initial: FiveWords, rounds: 8 | 12, fault?: { round: number; bit: number }): FiveWords {
  if (rounds !== 8 && rounds !== 12) throw new Error('Invalid rounds');
  let state = initial;
  RC.slice(12 - rounds).forEach((constant, index) => {
    if (fault && index === fault.round && fault.bit >= 0 && fault.bit < 320) state = flipStateBit(state, fault.bit);
    state = roundStages(state, constant).diffusion;
  });
  return state;
}

export function compareReplay(initial: FiveWords, rounds: 8 | 12, scenario: ReplayScenario, injectionRound: number, bit: number): ReplayAnalysis {
  if (!Number.isInteger(injectionRound) || injectionRound < 0 || injectionRound >= rounds) throw new Error('Invalid round');
  if (!Number.isInteger(bit) || bit < 0 || bit >= 320) throw new Error('Invalid bit');
  const golden = permute(initial, rounds);
  const checkpointShared = scenario === 'checkpoint_shared';
  const shared = checkpointShared ? flipStateBit(initial, bit) : initial;
  const replayOnlyCheckpoint = scenario === 'checkpoint_replay' ? flipStateBit(shared, bit) : shared;
  const firstFired = scenario === 'first_only' || scenario === 'dual_identical' || scenario === 'suppress_first_alarm';
  const replayFired = scenario === 'replay_only' || scenario === 'dual_identical' || scenario === 'suppress_replay_alarm';
  const suppress = scenario === 'suppress_replay_alarm' || scenario === 'suppress_first_alarm';
  const first = permute(shared, rounds, firstFired ? { round: injectionRound, bit } : undefined);
  const replay = permute(replayOnlyCheckpoint, rounds, replayFired ? { round: injectionRound, bit } : undefined);
  const rawMismatch = !wordsEqual(first, replay);
  const alarm = rawMismatch && !suppress;
  const valid = !rawMismatch || suppress;
  return { golden, first, replay, firstFired, replayFired,
    checkpointFired: checkpointShared || scenario === 'checkpoint_replay',
    rawMismatch, alarm, valid, incorrectRelease: valid && !wordsEqual(golden, replay) };
}
