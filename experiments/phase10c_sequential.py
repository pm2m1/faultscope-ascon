"""Bounded sequential SAT exploration of the real protected AEAD controller.

The *actual* ascon_aead_encrypt_temporal.sv is converted with sv2v. Only its
ascon_permutation_temporal child is replaced by a formal anyseq output stub.
This over-approximates permutation responses and is NOT a proof of the cipher,
full temporal permutation, physical faults, or unbounded controller safety.

Yosys SAT checks the controller I/O safety contract at every unrolled step,
requires clean/fault completion witnesses, and tests a source-level mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / 'rtl/ascon_aead_encrypt_temporal.sv'
DEFAULT_STEPS = 18
MAX_STEPS = 32

# The untrusted cryptographic submodule is replaced, NOT the controller logic.
# Independent arbitrary outputs intentionally include early/spurious done and
# inconsistent fault flags; the controller properties must hold despite them.
STUB = '''// FORMAL ABSTRACTION: permutation behavior is completely unconstrained.
// NOT a physical fault source, cycle-accurate permutation, or a cipher proof.
module ascon_permutation_temporal(
    input wire clk, rst_n, start_i,
    input wire [3:0] rounds_i,
    input wire [319:0] state_i,
    input wire fault_arm_i,
    input wire [3:0] fault_round_i,
    input wire [8:0] fault_bit_i,
    output wire fault_fired_o, fault_detected_o,
    output wire [319:0] state_o,
    output wire busy_o, done_o
);
    (* anyseq *) wire any_fired;
    (* anyseq *) wire any_detected;
    (* anyseq *) wire any_done;
    (* anyseq *) wire any_busy;
    (* anyseq *) wire [319:0] any_state;
    assign fault_fired_o = any_fired;
    assign fault_detected_o = any_detected;
    assign done_o = any_done;
    assign busy_o = any_busy;
    assign state_o = any_state;
endmodule
'''

TOP = '''// The controller is the real source-converted RTL; only its permutation
// child is abstracted to symbolic, arbitrary outputs in permutation_stub.v.
module phase10c_sequential_top(input wire clk,
    output wire policy_ok, cover_clean, cover_alarm);
    reg boot_reset_n = 1'b0;
    always @(posedge clk) boot_reset_n <= 1'b1;
    wire rst_n = boot_reset_n;

    (* anyseq *) wire start_i;
    (* anyseq *) wire [127:0] key_i, nonce_i, associated_data_i, plaintext_i;
    (* anyseq *) wire [4:0] ad_len_i, msg_len_i;
    (* anyseq *) wire fault_enable_i;
    (* anyseq *) wire [2:0] fault_phase_i;
    (* anyseq *) wire [3:0] fault_round_i;
    (* anyseq *) wire [8:0] fault_bit_i;

    wire fault_applied_o, fault_detected_o, result_valid_o;
    wire [127:0] ciphertext_o, tag_o;
    wire busy_o, done_o;

    ascon_aead_encrypt_temporal dut(
        .clk(clk), .rst_n(rst_n), .start_i(start_i),
        .key_i(key_i), .nonce_i(nonce_i),
        .associated_data_i(associated_data_i), .ad_len_i(ad_len_i),
        .plaintext_i(plaintext_i), .msg_len_i(msg_len_i),
        .fault_enable_i(fault_enable_i), .fault_phase_i(fault_phase_i),
        .fault_round_i(fault_round_i), .fault_bit_i(fault_bit_i),
        .fault_applied_o(fault_applied_o),
        .fault_detected_o(fault_detected_o),
        .result_valid_o(result_valid_o),
        .ciphertext_o(ciphertext_o), .tag_o(tag_o),
        .busy_o(busy_o), .done_o(done_o));

    reg prev_done = 1'b0;
    reg prev_reset = 1'b0;
    always @(posedge clk) begin
        prev_done <= done_o;
        prev_reset <= !rst_n;
    end

    wire outputs_masked = result_valid_o ||
        ((ciphertext_o == 128'd0) && (tag_o == 128'd0));
    wire alarm_blocks_release = !fault_detected_o || !result_valid_o;
    wire no_early_release = !busy_o || !result_valid_o;
    wire done_idle = !done_o || !busy_o;
    wire done_one_cycle = !prev_done || !done_o;
    wire reset_safe = !prev_reset ||
        (!busy_o && !done_o && !result_valid_o && !fault_detected_o &&
         ciphertext_o == 128'd0 && tag_o == 128'd0);
    // Reset is held for the first modeled cycle; no initial-state security
    // claim is made prior to the first reset edge.
    assign policy_ok = !rst_n || (outputs_masked && alarm_blocks_release &&
        no_early_release && done_idle && done_one_cycle && reset_safe);
    assign cover_clean = rst_n && done_o && result_valid_o && !fault_detected_o;
    assign cover_alarm = rst_n && done_o && fault_detected_o && !result_valid_o;
endmodule
'''

# Both mutations are deliberately confined to temporary copies of the original
# controller, never the committed RTL or verified experiment CSVs.
MUTATIONS = {
    'leak': (
        "assign ciphertext_o = result_valid_o ? ciphertext_q : 128'd0;",
        "assign ciphertext_o = ciphertext_q;",
    ),
    'alarm_bypass': (
        "if (fault_detected_o || perm_fault_detected) begin",
        "if (1'b0) begin",
    ),
}

SUCCESS = 'SAT proof finished - no model found: SUCCESS!'
COUNTEREXAMPLE = 'SAT proof finished - model found: FAIL!'


def mutate(source: str, kind: str) -> str:
    old, new = MUTATIONS[kind]
    if source.count(old) != 1:
        raise ValueError(f'Cannot uniquely locate {kind} safety-critical RTL statement')
    return source.replace(old, new, 1)


def check_source(source: str) -> None:
    if not re.search(r'\bmodule\s+ascon_aead_encrypt_temporal\b', source):
        raise ValueError('Unexpected controller module name')
    if source.count('ascon_permutation_temporal u_permutation') != 1:
        raise ValueError('Expected exactly one abstractable temporal permutation child')
    for kind, (old, _) in MUTATIONS.items():
        if source.count(old) != 1:
            raise ValueError(f'Source does not contain unique {kind} guard')
    for phrase in ('FINAL_WAIT: if (perm_done)', 'result_valid_o <= 1\'b0;',
                   'result_valid_o <= 1\'b1;', 'done_o <= 1\'b1;'):
        if phrase not in source:
            raise ValueError(f'Controller contract anchor missing: {phrase}')


def run_command(cmd: list[str], log: Path, timeout: int) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    data = p.stdout + '\n' + p.stderr
    log.write_text(data, encoding='utf-8')
    return p.returncode, data


def parse_verdict(rc: int, output: str, *, expect_counterexample: bool) -> bool:
    # Use no -verify in intentional counterexample runs. Any solver error,
    # timeout or unsupported cell must be rejected rather than counted as a hit.
    return rc == 0 and (
        COUNTEREXAMPLE in output if expect_counterexample else SUCCESS in output
    )


def prepare(out_dir: Path, source: str, sv2v: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'permutation_stub.v').write_text(STUB, encoding='utf-8')
    (out_dir / 'phase10c_sequential_top.v').write_text(TOP, encoding='utf-8')
    sv_source = out_dir / 'controller.sv'
    sv_source.write_text(source, encoding='utf-8')
    converted = out_dir / 'controller.v'
    rc, output = run_command([sv2v, str(sv_source.resolve())], out_dir / 'sv2v.log', 90)
    if rc != 0:
        raise AssertionError(f'sv2v could not convert controller; inspect {out_dir / "sv2v.log"}')
    if not re.search(r'\bmodule\s+ascon_aead_encrypt_temporal\b', output):
        raise AssertionError('sv2v did not emit the expected controller module')
    converted.write_text(output, encoding='utf-8')
    return converted, out_dir / 'permutation_stub.v'


def run_sat(out_dir: Path, *, property_name: str, expect_counterexample: bool,
            steps: int, yosys: str, converted: Path, stub: Path) -> Path:
    """Evaluate one bounded property with distinct, inspectable Yosys logs."""
    log = out_dir / f'{property_name}.log'
    top = out_dir / 'phase10c_sequential_top.v'
    options = f'-seq {steps} -set-init-zero -prove {property_name} '
    options += '0' if property_name.startswith('cover_') else '1'
    if not expect_counterexample:
        options += ' -verify'
    options += ' -show-inputs -show-outputs'
    script = (
        f'read_verilog -formal {converted.resolve()} {stub.resolve()} {top.resolve()}; '
        'hierarchy -check -top phase10c_sequential_top; '
        'proc; flatten; opt; async2sync; opt; dffunmap; opt; '
        f'sat {options}'
    )
    rc, output = run_command([yosys, '-Q', '-T', '-p', script], log, 180)
    if not parse_verdict(rc, output, expect_counterexample=expect_counterexample):
        raise AssertionError(f'Formal SAT {property_name} did not yield expected verdict; inspect {log}')
    return log


def run_campaign(out_dir: Path, *, steps: int = DEFAULT_STEPS,
                 source_path: Path = RTL, negative_controls: bool = True) -> dict:
    if not (12 <= steps <= MAX_STEPS):
        raise ValueError(f'Bound must be between 12 and {MAX_STEPS} clocks')
    yosys, sv2v = shutil.which('yosys'), shutil.which('sv2v')
    if not yosys or not sv2v:
        raise RuntimeError('Yosys and sv2v are required; install both before running the proof')
    original = source_path.read_text(encoding='utf-8')
    check_source(original)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'bounded sequential controller SAT with unconstrained permutation outputs',
              'clock_bound': steps, 'source_sha256': hashlib.sha256(original.encode()).hexdigest(),
              'yosys': None, 'sv2v': None, 'results': {}}
    for cmd, key in [([yosys, '-V'], 'yosys'), ([sv2v, '--numeric-version'], 'sv2v')]:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if p.returncode != 0:
            raise RuntimeError(f'{key} version query failed')
        report[key] = (p.stdout + p.stderr).strip().splitlines()[0]
    good_dir = out_dir / 'original'
    converted, stub = prepare(good_dir, original, sv2v)
    run_sat(good_dir, property_name='policy_ok', expect_counterexample=False,
            steps=steps, yosys=yosys, converted=converted, stub=stub)
    report['results']['policy_ok'] = 'PASS (no counterexample within bound)'
    print(f'PASS: original controller safety contract, {steps}-cycle bound')
    for name in ('cover_clean', 'cover_alarm'):
        run_sat(good_dir, property_name=name, expect_counterexample=True,
                steps=steps, yosys=yosys, converted=converted, stub=stub)
        report['results'][name] = 'REACHABLE within bound'
        print(f'PASS: reachability witness for {name}')
    if negative_controls:
        for kind in MUTATIONS:
            folder = out_dir / f'mutant_{kind}'
            altered, altered_stub = prepare(folder, mutate(original, kind), sv2v)
            run_sat(folder, property_name='policy_ok', expect_counterexample=True,
                    steps=steps, yosys=yosys, converted=altered, stub=altered_stub)
            report['results'][f'mutant_{kind}'] = 'COUNTEREXAMPLE observed'
            print(f'PASS: negative-control counterexample for {kind}')
    output = out_dir / 'phase10c_result.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Scope: bounded controller only; permutation internals are unconstrained, not proven')
    print(f'Report: {output}')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, default=Path('build/reproduction/phase10c'))
    parser.add_argument('--steps', type=int, default=DEFAULT_STEPS)
    args = parser.parse_args()
    run_campaign(args.out_dir, steps=args.steps)


if __name__ == '__main__':
    main()
