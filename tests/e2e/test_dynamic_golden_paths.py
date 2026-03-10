# pyright: reportMissingImports=false

import asyncio

import pytest

from dynamic_orchestration import Capability, DagPlanner, build_dynamic_planning_result
from tests.fakes import (
    FakeDagExecutor,
    FakeLLMClient,
    FakeMemoryStore,
    FakeSkillClassifier,
    FakeTeamComposer,
    build_registry_from_tuples,
)
from tests.fixtures.golden_routing_fallback import (
    GOLDEN_DYNAMIC_PLANNING_CASES,
    GOLDEN_ROUTING_FALLBACK_CASES,
    golden_case_ids,
)
from tests.integration.test_mcp_server_contracts import _FakePlanning, _load_mcp_server_module


@pytest.mark.e2e
@pytest.mark.parametrize(
    "case",
    GOLDEN_DYNAMIC_PLANNING_CASES,
    ids=golden_case_ids(GOLDEN_DYNAMIC_PLANNING_CASES),
)
def test_dynamic_planning_matches_golden_resolution(case, monkeypatch):
    monkeypatch.delenv("AI_ORCHESTRATOR_SKILLS_JSON", raising=False)

    result = build_dynamic_planning_result(
        task=case["task"],
        mode=case["mode"],
    )

    assert result.team_spec.mode == case["expected_resolved_mode"]
    assert result.team_spec.fallback_required is case["expected_fallback_required"]
    assert len(result.dag_plan.execution_order) >= 1


@pytest.mark.e2e
def test_fake_components_pipeline_is_deterministic():
    registry = build_registry_from_tuples(
        [
            ("planner-skill", "Planner", "Plans work"),
            ("developer-skill", "Developer", "Implements work"),
            ("verifier-skill", "Verifier", "Validates quality"),
        ]
    )
    classifier = FakeSkillClassifier(
        mapping={
            "planner-skill": (Capability.PLANNING,),
            "developer-skill": (Capability.IMPLEMENTATION,),
            "verifier-skill": (Capability.VERIFICATION,),
        }
    )
    composer = FakeTeamComposer(force_mode="implement")

    planning = build_dynamic_planning_result(
        task="Implement deterministic endpoint with tests",
        mode="auto",
        registry=registry,
        classifier=classifier,
        composer=composer,
        planner=DagPlanner(dynamic_edges=False),
    )

    executor = FakeDagExecutor()
    execution = executor.execute(planning.dag_plan.execution_order)

    memory = FakeMemoryStore()
    memory.add(
        {
            "mode": planning.team_spec.mode,
            "dag_order": list(planning.dag_plan.execution_order),
            "fallback_required": planning.team_spec.fallback_required,
        }
    )

    llm_client = FakeLLMClient(default_responses_by_agent={"planner": "{\"plan\":\"ok\"}"})
    llm_agent = llm_client.create_agent("planner", "Create a plan")
    response = asyncio.run(llm_agent.run([{"role": "user", "text": "Plan task"}]))

    assert planning.team_spec.mode == "implement"
    assert planning.team_spec.fallback_required is False
    assert execution["executed"] is True
    assert execution["node_count"] == len(planning.dag_plan.execution_order)
    assert memory.latest(1)[0]["dag_order"] == planning.dag_plan.execution_order
    assert response.text == "{\"plan\":\"ok\"}"
    assert len(llm_agent.calls) == 1


@pytest.mark.e2e
@pytest.mark.parametrize(
    "case",
    GOLDEN_ROUTING_FALLBACK_CASES,
    ids=golden_case_ids(GOLDEN_ROUTING_FALLBACK_CASES),
)
def test_autonomous_execute_golden_routing_e2e_lite(monkeypatch, case):
    mcp_server = _load_mcp_server_module()

    monkeypatch.setattr(
        mcp_server,
        "build_dynamic_planning_result",
        lambda **_kwargs: _FakePlanning(
            mode=case["planning_mode"],
            fallback_required=case["planning_fallback_required"],
            fallback_reasons=list(case["planning_fallback_reasons"]),
        ),
    )

    async def _collect(*_args, **_kwargs):
        if case["run_should_raise"]:
            raise TimeoutError("e2e-lite timeout")
        return {
            "phases_executed": ["PLAN", "EXECUTE", "VERIFY"],
            "final_status": case["run_final_status"],
            "iteration_count": 1,
            "outputs": [f"e2e:{case['id']}"],
            "success_indicators": {
                "completed": bool(case["run_completed"]),
                "verified": bool(case["run_completed"]),
            },
        }

    monkeypatch.setattr(mcp_server, "_collect_autonomous_run", _collect)

    result = asyncio.run(
        mcp_server.autonomous_execute(
            case["task"],
            mode=case["mode"],
            execution_mode=case["execution_mode"],
            max_loops=1,
            enable_legacy_fallback=True,
        )
    )

    assert result["effective_mode"] == case["expected_effective_mode"]
    assert result["fallback"]["triggered"] is case["expected_fallback_triggered"]
    assert result["fallback"]["mode_used"] == case["expected_fallback_mode"]
    assert isinstance(result["correlation_id"], str)
    assert result["correlation_id"]
    assert "telemetry" in result
    assert "discovery_success_rate" in result["telemetry"]
    assert "classification_confidence" in result["telemetry"]
    assert "dag_latency_ms" in result["telemetry"]
    assert "fallback_rate" in result["telemetry"]
