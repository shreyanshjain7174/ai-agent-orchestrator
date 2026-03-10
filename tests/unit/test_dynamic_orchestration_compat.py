# pyright: reportMissingImports=false

import json
import logging

from dynamic_orchestration import DagPlanner, EnvSkillRegistry, TeamComposer, build_default_registry


def _skills_payload(skill_id: str) -> str:
    return json.dumps(
        [
            {
                "id": skill_id,
                "name": f"{skill_id} name",
                "description": "Compatibility test skill",
                "source": "env",
                "health": "healthy",
            }
        ]
    )


def test_env_registry_supports_legacy_skills_json_alias(monkeypatch, caplog):
    monkeypatch.delenv("AI_ORCHESTRATOR_SKILLS_JSON", raising=False)
    monkeypatch.setenv("ORCHESTRATOR_SKILLS_JSON", _skills_payload("legacy-skill"))

    with caplog.at_level(logging.WARNING):
        discovered = EnvSkillRegistry().discover()

    assert len(discovered) == 1
    assert discovered[0].id == "legacy-skill"
    assert "ORCHESTRATOR_SKILLS_JSON" in caplog.text
    assert "AI_ORCHESTRATOR_SKILLS_JSON" in caplog.text


def test_env_registry_prefers_canonical_value_over_legacy_alias(monkeypatch, caplog):
    monkeypatch.setenv("AI_ORCHESTRATOR_SKILLS_JSON", _skills_payload("canonical-skill"))
    monkeypatch.setenv("ORCHESTRATOR_SKILLS_JSON", _skills_payload("legacy-skill"))

    with caplog.at_level(logging.WARNING):
        discovered = EnvSkillRegistry().discover()

    assert len(discovered) == 1
    assert discovered[0].id == "canonical-skill"
    assert "ORCHESTRATOR_SKILLS_JSON" not in caplog.text


def test_team_composer_supports_legacy_max_team_size_alias(monkeypatch, caplog):
    monkeypatch.delenv("AI_ORCHESTRATOR_MAX_TEAM_SIZE", raising=False)
    monkeypatch.setenv("MAX_TEAM_SIZE", "2")

    with caplog.at_level(logging.WARNING):
        composer = TeamComposer()

    assert composer.max_team_size == 2
    assert "MAX_TEAM_SIZE" in caplog.text
    assert "AI_ORCHESTRATOR_MAX_TEAM_SIZE" in caplog.text


def test_dag_planner_supports_legacy_dag_mode_alias(monkeypatch, caplog):
    monkeypatch.delenv("AI_ORCHESTRATOR_DAG_MODE", raising=False)
    monkeypatch.setenv("DAG_MODE", "static")

    with caplog.at_level(logging.WARNING):
        planner = DagPlanner()

    assert planner.dynamic_edges is False
    assert "DAG_MODE" in caplog.text
    assert "AI_ORCHESTRATOR_DAG_MODE" in caplog.text


def test_build_default_registry_supports_legacy_enable_skill_discovery_alias(monkeypatch, caplog):
    monkeypatch.delenv("AI_ORCHESTRATOR_ENABLE_SKILL_DISCOVERY", raising=False)
    monkeypatch.setenv("ENABLE_SKILL_DISCOVERY", "false")
    monkeypatch.setenv("AI_ORCHESTRATOR_SKILLS_JSON", _skills_payload("env-only-skill"))

    with caplog.at_level(logging.WARNING):
        registry = build_default_registry()
        discovered = registry.discover()

    assert any(skill.id == "planner-agent" for skill in discovered)
    assert all(skill.id != "env-only-skill" for skill in discovered)
    assert "ENABLE_SKILL_DISCOVERY" in caplog.text
    assert "AI_ORCHESTRATOR_ENABLE_SKILL_DISCOVERY" in caplog.text
