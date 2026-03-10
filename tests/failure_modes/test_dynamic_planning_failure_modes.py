# pyright: reportMissingImports=false

import json

from dynamic_orchestration import (
    Capability,
    RuleBasedSkillClassifier,
    SkillMetadata,
    StaticSkillRegistry,
    TaskProfile,
    TeamComposer,
    build_dynamic_planning_result,
)


def test_missing_required_capabilities_triggers_fallback():
    registry = StaticSkillRegistry(
        [
            SkillMetadata(
                id="implementation-only",
                name="Implementation Only",
                description="Implements features but no planning or verification",
                tags=("implementation",),
            )
        ]
    )

    result = build_dynamic_planning_result(
        task="Design secure architecture for auth service",
        mode="design",
        registry=registry,
    )

    assert result.team_spec.fallback_required is True
    assert any("planning" in reason or "verification" in reason for reason in result.team_spec.fallback_reasons)


def test_invalid_env_skill_payload_degrades_to_builtins(monkeypatch):
    monkeypatch.setenv("AI_ORCHESTRATOR_SKILLS_JSON", "{bad_json")

    result = build_dynamic_planning_result(
        task="Implement API endpoint",
        mode="implement",
    )

    assert len(result.discovered_skills) >= 1
    assert any(skill.source == "builtin" for skill in result.discovered_skills)


def test_auto_mode_detects_fix_bug_from_task_keywords():
    classifier = RuleBasedSkillClassifier()
    composer = TeamComposer()
    profile = TaskProfile(task="Fix login bug and regression", mode="auto")

    classified = classifier.classify(
        [
            SkillMetadata(
                id="planner",
                name="Planner",
                description="Task planning and orchestration",
                tags=("planning",),
            ),
            SkillMetadata(
                id="dev",
                name="Developer",
                description="Implement code fixes",
                tags=("implementation",),
            ),
            SkillMetadata(
                id="verify",
                name="Verifier",
                description="Testing and verification",
                tags=("testing", "verification"),
            ),
            SkillMetadata(
                id="eval",
                name="Evaluator",
                description="Evaluate quality and progress",
                tags=("evaluation",),
            ),
            SkillMetadata(
                id="research",
                name="Researcher",
                description="Research root causes",
                tags=("research",),
            ),
        ]
    )

    spec = composer.compose(profile, classified)

    assert spec.mode == "fix_bug"
    capabilities = {assignment.capability for assignment in spec.assignments}
    assert Capability.IMPLEMENTATION in capabilities


def test_classifier_marks_unknown_for_unrelated_descriptions():
    classifier = RuleBasedSkillClassifier()
    classified = classifier.classify(
        [
            SkillMetadata(
                id="other",
                name="Random Skill",
                description="This text has no known orchestration keywords.",
            )
        ]
    )

    assert classified[0].capabilities == (Capability.UNKNOWN,)
    assert classified[0].confidence_by_capability[Capability.UNKNOWN] >= 0.6


def test_dynamic_planning_result_is_json_serializable():
    result = build_dynamic_planning_result(
        task="Implement endpoint and tests",
        mode="auto",
    )

    payload = result.to_dict()
    encoded = json.dumps(payload)

    assert isinstance(encoded, str)
    assert "resolved_mode" in payload
