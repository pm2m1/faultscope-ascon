"""Phase 8B pure-TypeScript interactive Ascon trace cross-checked with Python reference.

Requires the already installed Node.js >=22.  Does not rely on a browser,
API, physical fault hook or external package installer.
"""
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest
from reference.ascon_permutation import MASK64, ROUND_CONSTANTS, ascon_round, ascon_permutation

ROOT = Path(__file__).resolve().parents[1]


def _node(script: str, data: object) -> object:
    node = shutil.which('node')
    assert node, 'Node.js >=22 is required to verify the educational TypeScript lab'
    proc = subprocess.run(
        [node, '--experimental-strip-types', '--input-type=module', '-e', script],
        cwd=ROOT, input=json.dumps(data), capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f'Node.js trace verification failed:\n{proc.stdout}\n{proc.stderr}'
    return json.loads(proc.stdout)


IMPORT = """import {asconTrace, compareReplay, flipStateBit, parseLaneHex, hex64, permute} from './frontend/src/asconTrace.ts';
let data=''; for await (const chunk of process.stdin) data += chunk;
const cases = JSON.parse(data);
"""


def test_trace_matches_officially_validated_python_reference_each_round():
    rng = random.Random(20261013)
    inputs = [tuple([0] * 5), tuple([MASK64] * 5), (1, 2, 3, 4, 5)]
    inputs.extend(tuple(rng.getrandbits(64) for _ in range(5)) for _ in range(17))
    cases = [{'state': [f'{w:016x}' for w in s], 'rounds': r} for s in inputs for r in (8, 12)]
    script = IMPORT + """console.log(JSON.stringify(cases.map(({state,rounds}) => {
      const frames=asconTrace(state.map(x=>BigInt('0x'+x)),rounds);
      return frames.map(({roundIndex,stage,constant,lanes})=>({roundIndex,stage,constant,lanes:lanes.map(hex64)}));
    })));"""
    outputs = _node(script, cases)
    assert len(outputs) == len(cases)
    for case, frames in zip(cases, outputs):
        rounds = case['rounds']
        assert len(frames) == 3 * rounds + 1
        words = tuple(int(h, 16) for h in case['state'])
        assert frames[0]['stage'] == 'input'
        assert frames[0]['lanes'] == case['state']
        for i, const in enumerate(ROUND_CONSTANTS[12 - rounds:]):
            a, b, c = frames[i * 3 + 1:i * 3 + 4]
            assert [a['stage'], b['stage'], c['stage']] == ['constant', 'substitution', 'diffusion']
            assert a['constant'] == b['constant'] == c['constant'] == const
            assert a['lanes'] == [f'{(w ^ const) if j == 2 else w:016x}' for j, w in enumerate(words)]
            words = ascon_round(words, const)
            assert c['lanes'] == [f'{w:016x}' for w in words]
        assert words == ascon_permutation(tuple(int(h, 16) for h in case['state']), rounds)


def _flip(state, bit):
    words = list(state)
    words[4 - bit // 64] ^= 1 << (bit % 64)
    return tuple(words)


def _py_permute(state, rounds, fault=None):
    for i, const in enumerate(ROUND_CONSTANTS[12 - rounds:]):
        if fault and i == fault[0]:
            state = _flip(state, fault[1])
        state = ascon_round(state, const)
    return state


def test_replay_fault_classifications_match_independent_python_model():
    rng = random.Random(72727)
    inputs = [tuple([0] * 5), tuple([MASK64] * 5)]
    inputs.extend(tuple(rng.getrandbits(64) for _ in range(5)) for _ in range(4))
    names = ['clean', 'first_only', 'replay_only', 'dual_identical', 'checkpoint_shared',
             'checkpoint_replay', 'suppress_replay_alarm', 'suppress_first_alarm']
    cases = [{'state': [f'{w:016x}' for w in state], 'rounds': r, 'scenario': name,
              'round': 2, 'bit': 319 if idx % 2 else 0}
             for idx, state in enumerate(inputs) for r in (8, 12) for name in names]
    script = IMPORT + """console.log(JSON.stringify(cases.map(({state,rounds,scenario,round,bit}) => {
      const o=compareReplay(state.map(v=>BigInt('0x'+v)),rounds,scenario,round,bit);
      return {first:o.first.map(hex64),replay:o.replay.map(hex64),golden:o.golden.map(hex64),
        rawMismatch:o.rawMismatch,alarm:o.alarm,valid:o.valid,incorrectRelease:o.incorrectRelease};
    })));"""
    outputs = _node(script, cases)
    for c, js in zip(cases, outputs):
        s = tuple(int(x, 16) for x in c['state'])
        name, rounds, bit = c['scenario'], c['rounds'], c['bit']
        sh = _flip(s, bit) if name == 'checkpoint_shared' else s
        replay_start = _flip(sh, bit) if name == 'checkpoint_replay' else sh
        first = _py_permute(sh, rounds, (c['round'], bit) if name in ('first_only', 'dual_identical', 'suppress_first_alarm') else None)
        replay = _py_permute(replay_start, rounds, (c['round'], bit) if name in ('replay_only', 'dual_identical', 'suppress_replay_alarm') else None)
        golden = _py_permute(s, rounds)
        raw = first != replay
        suppress = name in ('suppress_replay_alarm', 'suppress_first_alarm')
        alarm = raw and not suppress
        valid = not raw or suppress
        assert js == {
            'first': [f'{w:016x}' for w in first],
            'replay': [f'{w:016x}' for w in replay],
            'golden': [f'{w:016x}' for w in golden],
            'rawMismatch': raw, 'alarm': alarm, 'valid': valid,
            'incorrectRelease': valid and replay != golden,
        }


def test_hex_validation_and_exact_320_bit_mapping():
    script = IMPORT + """let s=[1n,2n,3n,4n,5n];console.log(JSON.stringify({
      good:['0','F','0123456789abcdef','0xABCD'].map(parseLaneHex).map(x=>x?.toString(16)),
      invalid:['','z','0123456789abcdef0','-2'].map(parseLaneHex),
      bit0:flipStateBit(s,0).map(hex64),bit319:flipStateBit(s,319).map(hex64),
      eight:permute([0n,0n,0n,0n,0n],8).map(hex64)
    }));"""
    result = _node(script, {})
    assert result['good'] == ['0', 'f', '123456789abcdef', 'abcd']
    assert result['invalid'] == [None] * 4
    assert result['bit0'] == [f'{x:016x}' for x in (1, 2, 3, 4, 4)]
    assert result['bit319'] == [f'{x:016x}' for x in ((1 << 63) + 1, 2, 3, 4, 5)]
    assert result['eight'] == [f'{x:016x}' for x in ascon_permutation((0,0,0,0,0),8)]
