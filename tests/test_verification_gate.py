"""
Verification gate: runs NuSMV against verification/model_v3.smv and fails
if ANY LTL specification comes back false. This is meant to run in CI
alongside the unit tests, so a code change that breaks a safety/liveness
property is caught automatically, not just when someone remembers to
run NuSMV by hand.

Run: pytest tests/test_verification_gate.py -v
"""

import subprocess
import shutil
import re
import pytest

MODEL_PATH = "verification/model_v3.smv"
NUSMV_BIN = shutil.which("NuSMV") or shutil.which("nusmv")


def run_nusmv(model_path: str) -> str:
    result = subprocess.run(
        [NUSMV_BIN, model_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout + result.stderr


def parse_spec_results(output: str) -> list[tuple[str, bool]]:
    """
    Parses lines like:
      -- specification  G (state = TERMINAL ->  G state = TERMINAL)  is true
      -- specification  G (...) is false
    Returns [(spec_text, is_true), ...]
    """
    results = []
    for line in output.splitlines():
        m = re.match(r"--\s*specification\s+(.*?)\s+is\s+(true|false)\s*$", line.strip())
        if m:
            spec_text, verdict = m.groups()
            results.append((spec_text, verdict == "true"))
    return results


@pytest.mark.skipif(NUSMV_BIN is None, reason="NuSMV not found on PATH")
def test_all_specifications_hold():
    output = run_nusmv(MODEL_PATH)
    results = parse_spec_results(output)

    assert results, f"No specification results parsed from NuSMV output:\n{output}"

    failed = [spec for spec, ok in results if not ok]
    assert not failed, (
        f"{len(failed)} of {len(results)} specification(s) FAILED:\n"
        + "\n".join(f"  - {spec}" for spec in failed)
        + f"\n\nFull NuSMV output:\n{output}"
    )


@pytest.mark.skipif(NUSMV_BIN is None, reason="NuSMV not found on PATH")
def test_expected_number_of_specifications_checked():
    """Guards against someone silently deleting a LTLSPEC line from the model."""
    output = run_nusmv(MODEL_PATH)
    results = parse_spec_results(output)
    assert len(results) == 4, f"Expected 4 specs (S1, S2, L1, L2), found {len(results)}"