# pyright: reportMissingImports=false

import json

from dynamic_orchestration import (
    CachedSkillRegistry,
    Capability,
    CompositeSkillRegistry,
    RuleBasedSkillClassifier,
    SkillMetadata,
    StaticSkillRegistry,
    TaskProfile,
    TeamComposer,
    build_dynamic_planning_result,
)

from tests.fakes import FakeSkillClassifier, build_registry_from_tuples


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


def test_retry_ceiling_is_enforced_for_persistent_timeouts():
    class AlwaysTimeoutRegistry:
        def __init__(self):
            self.calls = 0

        def discover(self):
            self.calls += 1
            raise TimeoutError("persistent timeout")

    registry = AlwaysTimeoutRegistry()
    cached = CachedSkillRegistry(registry, ttl_seconds=0.0, retry_attempts=2)

    discovered = cached.discover()

    assert discovered == []
    assert registry.calls == 3


def test_partial_failure_then_recovery_with_composite_registry():
    class TimeoutRegistry:
        def discover(self):
            raise TimeoutError("source timed out")

    class FlakyRecoveringRegistry:
        def __init__(self):
            self.calls = 0

        def discover(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary upstream error")
            return [
                SkillMetadata(
                    id="planner",
                    name="Planner",
                    description="Task planning and decomposition",
                    tags=("planning",),
                    health="healthy",
                ),
                SkillMetadata(
                    id="developer",
                    name="Developer",
                    description="Implement features and bug fixes",
                    tags=("implementation",),
                    health="healthy",
                ),
                SkillMetadata(
                    id="verifier",
                    name="Verifier",
                    description="Verify quality and tests",
                    tags=("verification", "testing"),
                    health="healthy",
                ),
            ]

    recovering = FlakyRecoveringRegistry()
    registry = CompositeSkillRegistry([TimeoutRegistry(), recovering], retry_attempts=1)

    result = build_dynamic_planning_result(
        task="Implement endpoint with tests",
        mode="implement",
        registry=registry,
    )

    assert recovering.calls == 2
    assert result.team_spec.fallback_required is False
    assert result.team_spec.mode == "implement"
    assert len(result.team_spec.assignments) >= 3


def test_timeout_behavior_uses_stale_cache_and_marks_health_degraded():
    class SequencedRegistry:
        def __init__(self):
            self.calls = 0

        def discover(self):
            self.calls += 1
            if self.calls == 1:
                return [
                    SkillMetadata(
                        id="planner",
                        name="Planner",
                        description="Task planning",
                        tags=("planning",),
                        health="healthy",
                    ),
                    SkillMetadata(
                        id="developer",
                        name="Developer",
                        description="Implement features",
                        tags=("implementation",),
                        health="healthy",
                    ),
                    SkillMetadata(
                        id="verifier",
                        name="Verifier",
                        description="Verify quality",
                        tags=("verification", "testing"),
                        health="healthy",
                    ),
                ]
            raise TimeoutError("upstream timeout after cache warmup")

    clock = {"now": 0.0}

    def _now() -> float:
        return clock["now"]

    cached = CachedSkillRegistry(
        SequencedRegistry(),
        ttl_seconds=0.0,
        retry_attempts=0,
        now_fn=_now,
    )

    initial = build_dynamic_planning_result(
        task="Implement endpoint with tests",
        mode="implement",
        registry=cached,
    )

    clock["now"] = 1.0
    degraded = build_dynamic_planning_result(
        task="Implement endpoint with tests",
        mode="implement",
        registry=cached,
    )

    assert initial.team_spec.fallback_required is False
    assert degraded.team_spec.fallback_required is False
    assert all(skill.health == "degraded" for skill in degraded.discovered_skills)


def test_bad_classification_recovers_with_fake_classifier_mapping():
    registry = build_registry_from_tuples(
        [
            ("planner-skill", "Planner", "Breaks work into plans"),
            ("developer-skill", "Developer", "Implements code and fixes"),
            ("verifier-skill", "Verifier", "Validates tests and quality"),
        ]
    )

    bad_classifier = FakeSkillClassifier(mapping={})
    bad_result = build_dynamic_planning_result(
        task="Implement endpoint with tests",
        mode="implement",
        registry=registry,
        classifier=bad_classifier,
    )

    recovered_classifier = FakeSkillClassifier(
        mapping={
            "planner-skill": (Capability.PLANNING,),
            "developer-skill": (Capability.IMPLEMENTATION,),
            "verifier-skill": (Capability.VERIFICATION,),
        }
    )
    recovered_result = build_dynamic_planning_result(
        task="Implement endpoint with tests",
        mode="implement",
        registry=registry,
        classifier=recovered_classifier,
    )

    assert bad_result.team_spec.fallback_required is True
    assert recovered_result.team_spec.fallback_required is False
    assert recovered_result.team_spec.mode == "implement"
