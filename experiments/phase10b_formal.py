"""Prove the *actual* protected RTL's combinational output-masking equations.

This is a Yosys SAT proof of two isolated, source-extracted output assignments.
It is NOT a sequential reachability proof, or a proof that alarms are raised.
A negative-control mutation must produce a real SAT counterexample.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "rtl/ascon_aead_encrypt_temporal.sv"
PORTS = ("ciphertext_o", "tag_o")


def extract_output_assignments(source: str) -> str:
    assignments = re.findall(r"(?m)^\s*assign\s+(ciphertext_o|tag_o)\s*=\s*([^;]+);", source)
    if len(assignments) != 2 or {port for port, _ in assignments} != set(PORTS):
        raise ValueError("Exactly one continuous assignment per external data output required")
    # Reject an additional procedural assignment to either output.
    for port in PORTS:
        if len(re.findall(rf"\b{port}\s*(?:<=|=(?!=))", source)) != 1:
            raise ValueError(f"Potential additional output driver for {port}")
    return "\n".join(f"assign {port} = {expr};" for port, expr in assignments)


def make_harness(source: str, negative_control: bool = False) -> str:
    assignments = extract_output_assignments(source)
    if negative_control:
        expected = "assign ciphertext_o = result_valid_o ? ciphertext_q : 128'd0;"
        if expected not in assignments:
            raise ValueError("Negative control cannot locate expected output mask")
        assignments = assignments.replace(expected, "assign ciphertext_o = ciphertext_q;")
    return f"""// Extracted directly from rtl/ascon_aead_encrypt_temporal.sv at run time.
module phase10b_output_gate_formal(
    input wire result_valid_o,
    input wire [127:0] ciphertext_q,
    input wire [127:0] tag_q,
    output wire [127:0] ciphertext_o,
    output wire [127:0] tag_o,
    output wire policy_ok
);
{assignments}
    // A purely combinational proof target. No $check/$assert cells are needed.
    // These conditions must hold for every valuation of the three inputs.
    assign policy_ok =
        (result_valid_o || (ciphertext_o == 128'd0 && tag_o == 128'd0)) &&
        (!result_valid_o || (ciphertext_o == ciphertext_q && tag_o == tag_q));
endmodule
"""


def run_proof(out_dir: Path, *, negative_control: bool = False,
              source_path: Path = SOURCE, yosys: str | None = None) -> tuple[bool, Path]:
    executable = yosys or shutil.which("yosys")
    if not executable:
        raise RuntimeError("Yosys is required for SAT output-policy proof")
    out_dir.mkdir(parents=True, exist_ok=True)
    label = "negative" if negative_control else "positive"
    harness = out_dir / f"output_gate_{label}.v"
    harness.write_text(make_harness(source_path.read_text(), negative_control=negative_control))
    log = out_dir / f"output_gate_{label}.log"
    # For a deliberately broken circuit, ask Yosys to *show* a counterexample
    # without -verify. Older Yosys versions abort with an ERROR under -verify
    # before emitting a machine-checkable "model found: FAIL!" verdict.
    sat_options = "-prove policy_ok 1 -show-inputs -show-outputs"
    if not negative_control:
        sat_options = "-verify " + sat_options
    script = (
        f"read_verilog {harness.resolve()}; "
        "prep -top phase10b_output_gate_formal; "
        f"sat {sat_options}"
    )
    proc = subprocess.run([executable, "-Q", "-T", "-p", script], capture_output=True, text=True, timeout=90)
    output = proc.stdout + "\n" + proc.stderr
    log.write_text(output)
    # The SAT command solves for any counterexample to policy_ok == 1.
    # Both success and intentional failure require explicit SAT verdicts.
    # In particular, a solver error with a nonzero exit status is NOT a
    # successful negative control.
    verdict_success = "SAT proof finished - no model found: SUCCESS!" in output
    verdict_counterexample = "SAT proof finished - model found: FAIL!" in output
    if negative_control:
        if proc.returncode != 0 or not verdict_counterexample:
            raise AssertionError(f"Negative control did not produce a SAT counterexample: {log}")
        return True, log
    if proc.returncode != 0 or not verdict_success:
        raise AssertionError(f"Output-mask SAT proof failed or gave no proof verdict: {log}")
    return True, log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("build/reproduction/phase10b/formal"))
    args = parser.parse_args()
    run_proof(args.out_dir)
    print("PASS: extracted RTL output-mask and valid-release SAT proof")
    run_proof(args.out_dir, negative_control=True)
    print("PASS: deliberately broken mask yields SAT counterexample")
    print("Scope: combinational assignments only; FSM/alarm temporal behavior NOT proven")


if __name__ == "__main__":
    main()
