# pyright: reportMissingImports=false

from pathlib import Path

from dynamic_orchestration import DagPlanner


REPO_ROOT = Path(__file__).resolve().parents[2]


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
    assert "AI_ORCHESTRATOR_ENABLE_SKILL_DISCOVERY" in env_example
    assert "ENABLE_SKILL_DISCOVERY" in env_example


def test_translation_smoke_legacy_dag_mode_alias(monkeypatch):
    monkeypatch.delenv("AI_ORCHESTRATOR_DAG_MODE", raising=False)
    monkeypatch.setenv("DAG_MODE", "static")

    planner = DagPlanner()

    assert planner.dynamic_edges is False
