from __future__ import annotations

from typing import Any


GOLDEN_ROUTING_FALLBACK_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "auto_dynamic_success",
        "task": "Implement deterministic validation middleware",
        "mode": "implement",
        "execution_mode": "auto",
        "planning_mode": "implement",
        "planning_fallback_required": False,
        "planning_fallback_reasons": (),
        "run_should_raise": False,
        "run_final_status": "COMPLETE",
        "run_completed": True,
        "expected_effective_mode": "implement",
        "expected_fallback_triggered": False,
        "expected_fallback_mode": "dynamic",
    },
    {
        "id": "auto_planning_fallback_to_legacy",
        "task": "Design resilient auth architecture",
        "mode": "auto",
        "execution_mode": "auto",
        "planning_mode": "design",
        "planning_fallback_required": True,
        "planning_fallback_reasons": ("Missing capability 'architecture' for mode 'design'.",),
        "run_should_raise": False,
        "run_final_status": "COMPLETE",
        "run_completed": True,
        "expected_effective_mode": "legacy",
        "expected_fallback_triggered": True,
        "expected_fallback_mode": "legacy",
    },
    {
        "id": "dynamic_mode_keeps_dynamic_even_when_planning_flags_fallback",
        "task": "Design resilient auth architecture",
        "mode": "auto",
        "execution_mode": "dynamic",
        "planning_mode": "design",
        "planning_fallback_required": True,
        "planning_fallback_reasons": ("Missing capability 'architecture' for mode 'design'.",),
        "run_should_raise": False,
        "run_final_status": "COMPLETE",
        "run_completed": True,
        "expected_effective_mode": "design",
        "expected_fallback_triggered": False,
        "expected_fallback_mode": "dynamic",
    },
    {
        "id": "auto_runtime_timeout_fallback_to_legacy",
        "task": "Implement endpoint and run tests",
        "mode": "implement",
        "execution_mode": "auto",
        "planning_mode": "implement",
        "planning_fallback_required": False,
        "planning_fallback_reasons": (),
        "run_should_raise": True,
        "run_final_status": "COMPLETE",
        "run_completed": True,
        "expected_effective_mode": "legacy",
        "expected_fallback_triggered": True,
        "expected_fallback_mode": "legacy",
    },
    {
        "id": "dynamic_runtime_timeout_no_legacy_fallback",
        "task": "Implement endpoint and run tests",
        "mode": "implement",
        "execution_mode": "dynamic",
        "planning_mode": "implement",
        "planning_fallback_required": False,
        "planning_fallback_reasons": (),
        "run_should_raise": True,
        "run_final_status": "COMPLETE",
        "run_completed": True,
        "expected_effective_mode": "implement",
        "expected_fallback_triggered": False,
        "expected_fallback_mode": "dynamic",
    },
)


GOLDEN_DYNAMIC_PLANNING_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "auto_fix_bug_resolution",
        "task": "Fix login bug and add regression tests",
        "mode": "auto",
        "expected_resolved_mode": "fix_bug",
        "expected_fallback_required": True,
    },
    {
        "id": "auto_design_resolution",
        "task": "Design event driven workflow for payments",
        "mode": "auto",
        "expected_resolved_mode": "design",
        "expected_fallback_required": False,
    },
    {
        "id": "explicit_refactor_resolution",
        "task": "Modernize and refactor orchestration module",
        "mode": "refactor",
        "expected_resolved_mode": "refactor",
        "expected_fallback_required": False,
    },
)


def golden_case_ids(cases: tuple[dict[str, Any], ...]) -> list[str]:
    return [str(case["id"]) for case in cases]
