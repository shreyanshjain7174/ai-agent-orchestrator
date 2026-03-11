#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.fixtures.perf_harness import build_performance_profile, render_markdown_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic autonomous execution performance baseline artifacts.",
    )
    parser.add_argument("--iterations", type=int, default=30, help="Per-mode iteration count.")
    parser.add_argument(
        "--concurrency-batches",
        type=int,
        default=2,
        help="Number of deterministic batches for each concurrent scenario.",
    )
    parser.add_argument(
        "--memory-repeats",
        type=int,
        default=2,
        help="Number of repeats per memory trend scenario.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "docs" / "performance-baseline.json",
        help="Output path for JSON baseline.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPO_ROOT / "docs" / "performance-baseline.md",
        help="Output path for Markdown report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    profile = build_performance_profile(
        iterations=max(1, int(args.iterations)),
        concurrency_batches=max(1, int(args.concurrency_batches)),
        memory_repeats=max(1, int(args.memory_repeats)),
    )

    output_path = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    report_path = args.report if args.report.is_absolute() else REPO_ROOT / args.report

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown_report(profile) + "\n", encoding="utf-8")

    print(f"Wrote JSON baseline: {output_path}")
    print(f"Wrote Markdown report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
