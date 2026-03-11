# pyright: reportMissingImports=false

from __future__ import annotations

import json
from pathlib import Path

from tests.fixtures.perf_harness import (
    load_mcp_server_module,
    profile_concurrent_load,
    profile_execution_modes,
    profile_memory_trends,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_baseline() -> dict:
    baseline_path = REPO_ROOT / "docs" / "performance-baseline.json"
    return json.loads(baseline_path.read_text(encoding="utf-8"))


def test_execution_mode_smoke_within_soft_budgets():
    baseline = _load_baseline()
    budgets = baseline["soft_budgets"]

    mcp_server = load_mcp_server_module()
    current = profile_execution_modes(
        mcp_server,
        iterations=6,
        mode="implement",
        max_loops=1,
    )

    for mode in ("legacy", "dynamic", "auto"):
        mode_budget = budgets["mode_latency_ms"][mode]
        mode_current = current[mode]
        latency = mode_current["latency_ms"]

        assert latency["median"] <= mode_budget["median_max"]
        assert latency["p95"] <= mode_budget["p95_max"]
        assert mode_current["fallback_rate"] <= budgets["fallback_rate_max"]

        ratio_budget = budgets["execution_order_valid_ratio_min"].get(mode)
        ratio_current = mode_current["execution_order_valid_ratio"]
        if ratio_budget is not None and ratio_current is not None:
            assert ratio_current >= ratio_budget


def test_concurrency_and_memory_smoke_within_soft_budgets():
    baseline = _load_baseline()
    budgets = baseline["soft_budgets"]

    mcp_server = load_mcp_server_module()
    current_load = profile_concurrent_load(
        mcp_server,
        execution_modes=("legacy", "dynamic", "auto"),
        parallelism_values=(2, 4),
        batches=1,
    )

    for scenario in current_load["scenarios"]:
        scenario_budget = budgets["concurrency"][scenario["key"]]
        assert scenario["throughput_rps"] >= scenario_budget["throughput_min"]
        assert scenario["latency_ms"]["p95"] <= scenario_budget["p95_max"]

    current_memory = profile_memory_trends(mcp_server, repeats=1)
    memory_budget = budgets["memory_kib"]
    memory_summary = current_memory["summary"]

    assert memory_summary["peak_kib_max"] <= memory_budget["peak_kib_max"]
    assert memory_summary["peak_growth_ratio"] <= memory_budget["peak_growth_ratio_max"]
