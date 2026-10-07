"""CI evaluation gate: runs the fixed scenario set against a fixed seed and fails the build
if detection quality regresses. This is what makes "a merge is blocked when quality
regresses" (programme rule N4) real rather than a claim.

    python -m teleguard.evaluate.gate pipelines/web_analytics
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from teleguard.contracts.model import load_contract
from teleguard.evaluate.baselines import build_baseline_store
from teleguard.evaluate.comparison_systems import b0_no_checks, b1_naive_schema_only, ours
from teleguard.evaluate.engine import evaluate
from teleguard.evaluate.report import write_report
from teleguard.inject.scenarios import default_scenarios
from teleguard.tracer import load_module

# Set with margin below the measured result (precision 1.00, recall 0.86, lag 0.0) on the
# fixed seed below, so the gate catches a real regression without being flaky on noise.
MIN_PRECISION = 0.90
MIN_RECALL = 0.70
MAX_MEAN_LAG_BATCHES = 2.0


def run(pipeline_dir: Path, out_dir: Path) -> int:
    legacy = load_module(pipeline_dir / "legacy" / "run.py")
    contract = load_contract(pipeline_dir / "contracts.yaml")
    scenarios = default_scenarios(onset_batch=4)

    baselines = build_baseline_store(legacy, n_batches=15, events_per_batch=3000)
    reports = [
        evaluate("B0", legacy, contract, b0_no_checks(), scenarios, n_batches=10, events_per_batch=3000),
        evaluate("B1", legacy, contract, b1_naive_schema_only(), scenarios, n_batches=10, events_per_batch=3000),
        evaluate("ours", legacy, contract, ours(contract, baselines), scenarios,
                n_batches=10, events_per_batch=3000),
    ]
    write_report(reports, out_dir)

    ours_report = reports[-1]
    problems = []
    if ours_report.precision < MIN_PRECISION:
        problems.append(f"precision {ours_report.precision:.2f} below minimum {MIN_PRECISION}")
    if ours_report.recall < MIN_RECALL:
        problems.append(f"recall {ours_report.recall:.2f} below minimum {MIN_RECALL}")
    if ours_report.mean_lag_batches is not None and ours_report.mean_lag_batches > MAX_MEAN_LAG_BATCHES:
        problems.append(f"mean lag {ours_report.mean_lag_batches:.1f} batches above maximum "
                        f"{MAX_MEAN_LAG_BATCHES}")

    if problems:
        print("EVALUATION GATE FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"Evaluation gate passed: precision={ours_report.precision:.2f} "
          f"recall={ours_report.recall:.2f} mean_lag={ours_report.mean_lag_batches}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="teleguard.evaluate.gate")
    parser.add_argument("pipeline_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("eval_report"))
    args = parser.parse_args(argv)
    return run(args.pipeline_dir, args.out)


if __name__ == "__main__":
    sys.exit(main())
