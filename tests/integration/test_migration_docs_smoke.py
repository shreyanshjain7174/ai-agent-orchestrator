# pyright: reportMissingImports=false

import importlib
import json
import sys
import types
from pathlib import Path

from dynamic_orchestration import DagPlanner


REPO_ROOT = Path(__file__).resolve().parents[2]


def _install_backtest_suite_stubs() -> None:
    agent_framework = types.ModuleType("agent_framework")

    class ChatMessage:
        def __init__(self, role: str, text: str = ""):
            self.role = role
            self.text = text

    class WorkflowOutputEvent:
        def __init__(self, data):
            self.data = data

    class WorkflowStatusEvent:
        def __init__(self, state):
            self.state = state

    agent_framework.ChatMessage = ChatMessage
    agent_framework.WorkflowOutputEvent = WorkflowOutputEvent
    agent_framework.WorkflowStatusEvent = WorkflowStatusEvent
    sys.modules["agent_framework"] = agent_framework

    autonomous = types.ModuleType("autonomous_orchestrator")

    class MemorySystem:
        def __init__(self, memory_dir: str = ".backtest_memory"):
            _ = memory_dir
            self.memories = []

        def add_memory(self, **kwargs):
            self.memories.append(kwargs)

        def get_relevant_memories(self, task_type: str, issue_keywords: list[str]):
            _ = (task_type, issue_keywords)
            return list(self.memories)

    def create_autonomous_workflow():
        class _Workflow:
            async def run_stream(self, _messages):
                if False:
                    yield WorkflowOutputEvent("noop")

        return _Workflow()

    autonomous.MemorySystem = MemorySystem
    autonomous.create_autonomous_workflow = create_autonomous_workflow
    sys.modules["autonomous_orchestrator"] = autonomous


def _load_backtest_suite_module():
    _install_backtest_suite_stubs()
    sys.modules.pop("backtest_suite", None)
    return importlib.import_module("backtest_suite")


def test_migration_matrix_doc_contains_required_sections():
    migration_doc = (REPO_ROOT / "docs" / "migration-matrix.md").read_text(encoding="utf-8")

    assert "Migration Matrix" in migration_doc
    assert "Safe Upgrade Steps" in migration_doc
    assert "AI_ORCHESTRATOR_DISCOVERY_RETRY_ATTEMPTS" in migration_doc
    assert "DISCOVERY_RETRY_ATTEMPTS" in migration_doc
    assert "execution_mode" in migration_doc


def test_readme_and_env_example_reference_migration_guidance():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "docs/migration-matrix.md" in readme
    assert "docs/dynamic-orchestration-architecture.md" in readme
    assert "docs/operations-runbook.md" in readme
    assert "docs/performance-baseline.md" in readme
    assert "docs/performance-baseline.json" in readme
    assert "scripts/profile_execution_paths.py" in readme
    assert "AI_ORCHESTRATOR_ENABLE_SKILL_DISCOVERY" in env_example
    assert "ENABLE_SKILL_DISCOVERY" in env_example


def test_dynamic_architecture_and_operations_runbook_docs():
    architecture_doc = (
        REPO_ROOT / "docs" / "dynamic-orchestration-architecture.md"
    ).read_text(encoding="utf-8")
    runbook_doc = (REPO_ROOT / "docs" / "operations-runbook.md").read_text(encoding="utf-8")

    assert "Dynamic Orchestration Architecture" in architecture_doc
    assert "correlation_id" in architecture_doc
    assert "telemetry" in architecture_doc
    assert "fallback_rate" in architecture_doc

    assert "Operations Runbook" in runbook_doc
    assert "Rollout Plan" in runbook_doc
    assert "Rollback Plan" in runbook_doc
    assert "Troubleshooting" in runbook_doc
    assert "Performance Baseline Procedure" in runbook_doc
    assert "tests/integration/test_performance_smoke.py" in runbook_doc


def test_performance_baseline_docs_contract_shape():
    baseline_json = json.loads(
        (REPO_ROOT / "docs" / "performance-baseline.json").read_text(encoding="utf-8")
    )
    baseline_md = (REPO_ROOT / "docs" / "performance-baseline.md").read_text(encoding="utf-8")

    assert baseline_json["schema_version"] == 1
    assert baseline_json["deterministic_offline"] is True
    assert "execution_modes" in baseline_json
    assert "concurrent_load" in baseline_json
    assert "memory_trends" in baseline_json
    assert "soft_budgets" in baseline_json

    for mode in ("legacy", "dynamic", "auto"):
        assert mode in baseline_json["execution_modes"]
        assert "latency_ms" in baseline_json["execution_modes"][mode]
        assert "fallback_rate" in baseline_json["execution_modes"][mode]

    assert "Performance Baseline" in baseline_md
    assert "Execution Mode Results" in baseline_md
    assert "Concurrent Load Results" in baseline_md
    assert "Memory Trend Results" in baseline_md
    assert "Optimization Recommendations" in baseline_md


def test_backtest_operational_comparison_contract_with_stubbed_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    backtest_suite = _load_backtest_suite_module()

    results = backtest_suite.BacktestResults()
    results.add_test(
        test_name="dynamic-sample",
        mode="design",
        success=True,
        iterations=2,
        duration=1.2,
        output="ok",
    )
    results.add_test(
        test_name="legacy-sample",
        mode="legacy",
        success=False,
        iterations=1,
        duration=1.5,
        output="fail",
        error="legacy failure",
    )

    comparison = results.get_operational_comparison()

    assert "dynamic" in comparison
    assert "legacy" in comparison
    assert "deltas" in comparison
    assert comparison["dynamic"]["total_tests"] == 1
    assert comparison["legacy"]["total_tests"] == 1
    assert comparison["legacy_coverage"] is True
    assert comparison["deltas"]["success_rate_pct"] is not None

    suite = backtest_suite.BacktestSuite()
    suite.results = results
    suite._generate_report()

    report = (tmp_path / "backtest_report.json").read_text(encoding="utf-8")
    assert "operational_comparison" in report


def test_translation_smoke_legacy_dag_mode_alias(monkeypatch):
    monkeypatch.delenv("AI_ORCHESTRATOR_DAG_MODE", raising=False)
    monkeypatch.setenv("DAG_MODE", "static")

    planner = DagPlanner()

    assert planner.dynamic_edges is False
