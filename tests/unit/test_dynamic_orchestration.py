# pyright: reportMissingImports=false

import json

from dynamic_orchestration import (
    CachedSkillRegistry,
    Capability,
    ClassifiedSkill,
    CompositeSkillRegistry,
    DagPlanner,
    EnvSkillRegistry,
    RuleBasedSkillClassifier,
    SkillMetadata,
    StaticSkillRegistry,
    TaskProfile,
    TeamAssignment,
    TeamComposer,
    TeamSpec,
    build_dynamic_planning_result,
    default_static_skills,
)


def test_env_skill_registry_parses_valid_payload(monkeypatch):
    payload = [
        {
            "id": "python-pro",
            "name": "Python Pro",
            "description": "Expert Python implementation and testing",
            "source": "env",
            "tags": ["python", "implementation", "testing"],
            "input_schema_summary": "{code: string, files?: string[]}",
            "health": "healthy",
        }
    ]
    monkeypatch.setenv("AI_ORCHESTRATOR_SKILLS_JSON", json.dumps(payload))

    registry = EnvSkillRegistry()
    discovered = registry.discover()

    assert len(discovered) == 1
    assert discovered[0].id == "python-pro"
    assert "implementation" in discovered[0].tags
    assert discovered[0].input_schema_summary.startswith("{")


def test_env_skill_registry_gracefully_handles_invalid_json(monkeypatch):
    monkeypatch.setenv("AI_ORCHESTRATOR_SKILLS_JSON", "{invalid json")

    registry = EnvSkillRegistry()
    discovered = registry.discover()

    assert discovered == []


def test_rule_based_classifier_assigns_expected_capabilities():
    classifier = RuleBasedSkillClassifier()
    skill = SkillMetadata(
        id="security-reviewer",
        name="Security Reviewer",
        description="Performs security audit, testing, and vulnerability review.",
        tags=("security", "testing", "audit"),
    )

    classified = classifier.classify([skill])[0]

    assert Capability.SECURITY in classified.capabilities
    assert Capability.TESTING in classified.capabilities
    assert classified.confidence_by_capability[Capability.SECURITY] >= 0.6


def test_team_composer_requires_fallback_when_required_capability_missing():
    implementation_skill = ClassifiedSkill(
        skill=SkillMetadata(
            id="developer-agent",
            name="Developer Agent",
            description="Implements code",
            tags=("implementation",),
        ),
        capabilities=(Capability.IMPLEMENTATION,),
        confidence_by_capability={Capability.IMPLEMENTATION: 0.9},
    )

    composer = TeamComposer()
    spec = composer.compose(
        TaskProfile(task="Design a scalable architecture", mode="design"),
        [implementation_skill],
    )

    assert spec.mode == "design"
    assert spec.fallback_required is True
    assert len(spec.fallback_reasons) >= 1


def test_dag_planner_builds_acyclic_execution_order():
    spec = TeamSpec(
        mode="implement",
        assignments=[
            TeamAssignment("planner", Capability.PLANNING, "planner-agent", 0.9),
            TeamAssignment("developer", Capability.IMPLEMENTATION, "developer-agent", 0.9),
            TeamAssignment("verifier", Capability.VERIFICATION, "verifier-agent", 0.9),
        ],
    )

    dag = DagPlanner().plan(spec)

    assert dag.execution_order.index("planner") < dag.execution_order.index("developer")
    assert dag.execution_order.index("developer") < dag.execution_order.index("verifier")


def test_dynamic_planning_result_is_deterministic_for_same_input():
    static_registry = StaticSkillRegistry(default_static_skills())

    first = build_dynamic_planning_result(
        task="Fix authentication bug and add regression tests",
        mode="auto",
        registry=static_registry,
    ).to_dict()
    second = build_dynamic_planning_result(
        task="Fix authentication bug and add regression tests",
        mode="auto",
        registry=static_registry,
    ).to_dict()

    assert first == second
    assert first["resolved_mode"] in {"fix_bug", "debug", "implement", "design", "refactor"}


def test_composite_registry_handles_partial_source_failures():
    class TimeoutRegistry:
        def discover(self):
            raise TimeoutError("source timeout")

    class HealthyRegistry:
        def discover(self):
            return [
                SkillMetadata(
                    id="healthy-source",
                    name="Healthy Source",
                    description="Reliable planning provider",
                    source="fixture",
                    input_schema_summary="{task: string}",
                    health="healthy",
                )
            ]

    registry = CompositeSkillRegistry([TimeoutRegistry(), HealthyRegistry()], retry_attempts=1)
    discovered = registry.discover()

    assert len(discovered) == 1
    assert discovered[0].id == "healthy-source"
    assert discovered[0].health == "healthy"


def test_cached_registry_retries_after_timeout_before_failing():
    class FlakyRegistry:
        def __init__(self):
            self.calls = 0

        def discover(self):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("first call timed out")
            return [
                SkillMetadata(
                    id="recovered",
                    name="Recovered",
                    description="Recovered after retry",
                    health="healthy",
                )
            ]

    flaky = FlakyRegistry()
    cached = CachedSkillRegistry(flaky, ttl_seconds=0.0, retry_attempts=1)

    discovered = cached.discover()

    assert len(discovered) == 1
    assert flaky.calls == 2


def test_cached_registry_falls_back_to_stale_inventory_on_timeout():
    class SequencedRegistry:
        def __init__(self):
            self.calls = 0

        def discover(self):
            self.calls += 1
            if self.calls == 1:
                return [
                    SkillMetadata(
                        id="cached-skill",
                        name="Cached Skill",
                        description="Used for stale fallback",
                        health="healthy",
                    )
                ]
            raise TimeoutError("upstream timeout")

    clock = {"value": 0.0}

    def _now() -> float:
        return clock["value"]

    registry = SequencedRegistry()
    cached = CachedSkillRegistry(registry, ttl_seconds=0.0, retry_attempts=0, now_fn=_now)

    fresh = cached.discover()
    clock["value"] = 1.0
    stale = cached.discover()

    assert fresh[0].id == "cached-skill"
    assert stale[0].id == "cached-skill"
    assert stale[0].health == "degraded"
