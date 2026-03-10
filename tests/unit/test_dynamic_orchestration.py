# pyright: reportMissingImports=false

import json
import threading

import pytest

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


def test_dag_planner_cycle_validation_failure_path():
    class _CyclicDagPlanner(DagPlanner):
        def _build_dynamic_dependency_map(self, node_by_role, mode):
            _ = mode
            return {
                "planner": {"developer"},
                "developer": {"planner"},
            }

    spec = TeamSpec(
        mode="implement",
        assignments=[
            TeamAssignment("planner", Capability.PLANNING, "planner-agent", 0.9),
            TeamAssignment("developer", Capability.IMPLEMENTATION, "developer-agent", 0.9),
        ],
    )

    with pytest.raises(ValueError, match="Cycle detected while building DAG plan"):
        _CyclicDagPlanner(dynamic_edges=True).plan(spec)


def test_dag_planner_max_nodes_guard_raises():
    spec = TeamSpec(
        mode="implement",
        assignments=[
            TeamAssignment("planner", Capability.PLANNING, "planner-agent", 0.9),
            TeamAssignment("developer", Capability.IMPLEMENTATION, "developer-agent", 0.9),
        ],
    )

    with pytest.raises(ValueError, match="max_nodes=1"):
        DagPlanner(max_nodes=1).plan(spec)


def test_dag_planner_static_vs_dynamic_edges_via_explicit_flag(monkeypatch):
    monkeypatch.setenv("AI_ORCHESTRATOR_DAG_MODE", "static")

    spec = TeamSpec(
        mode="implement",
        assignments=[
            TeamAssignment("planner", Capability.PLANNING, "planner-agent", 0.95),
            TeamAssignment("architect", Capability.ARCHITECTURE, "architect-agent", 0.95),
            TeamAssignment("developer", Capability.IMPLEMENTATION, "developer-agent", 0.95),
            TeamAssignment("verifier", Capability.VERIFICATION, "verifier-agent", 0.95),
        ],
    )

    static_plan = DagPlanner(dynamic_edges=False).plan(spec)
    dynamic_plan = DagPlanner(dynamic_edges=True).plan(spec)

    static_by_id = {node.id: set(node.depends_on) for node in static_plan.nodes}
    dynamic_by_id = {node.id: set(node.depends_on) for node in dynamic_plan.nodes}

    assert static_by_id["verifier"] == {"developer"}
    assert "architect" in dynamic_by_id["verifier"]
    assert static_by_id["developer"] == {"planner"}
    assert "architect" in dynamic_by_id["developer"]


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


def test_cached_registry_serializes_concurrent_refreshes():
    class SlowRegistry:
        def __init__(self):
            self.calls = 0
            self.started = threading.Event()
            self.release = threading.Event()

        def discover(self):
            self.calls += 1
            self.started.set()
            self.release.wait(timeout=1.0)
            return [
                SkillMetadata(
                    id="shared-skill",
                    name="Shared Skill",
                    description="Discovery should run once under contention",
                    health="healthy",
                )
            ]

    registry = SlowRegistry()
    cached = CachedSkillRegistry(registry, ttl_seconds=60.0, retry_attempts=0)

    results: list[list[SkillMetadata]] = []
    errors: list[Exception] = []

    def _worker() -> None:
        try:
            results.append(cached.discover())
        except Exception as exc:  # pragma: no cover - defensive guard for threaded test
            errors.append(exc)

    first = threading.Thread(target=_worker)
    second = threading.Thread(target=_worker)

    first.start()
    assert registry.started.wait(timeout=1.0)
    second.start()

    registry.release.set()

    first.join(timeout=1.0)
    second.join(timeout=1.0)

    assert not errors
    assert registry.calls == 1
    assert len(results) == 2
    assert all(items and items[0].id == "shared-skill" for items in results)
