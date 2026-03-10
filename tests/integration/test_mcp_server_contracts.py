# pyright: reportMissingImports=false

import asyncio
import importlib
import json
import logging
import sys
import types
from types import SimpleNamespace

import pytest

from tests.fakes import FakeLLMClient
from tests.fixtures.golden_routing_fallback import GOLDEN_ROUTING_FALLBACK_CASES, golden_case_ids


def _install_mcp_server_stubs() -> None:
    """Install lightweight stubs so mcp_server can be imported in CI without external SDKs."""
    agent_framework = types.ModuleType("agent_framework")

    class ChatMessage:
        def __init__(self, role: str, text: str = ""):
            self.role = role
            self.text = text

    class AgentExecutorRequest:
        def __init__(self, messages, should_respond: bool = True):
            self.messages = messages
            self.should_respond = should_respond

    class WorkflowOutputEvent:
        def __init__(self, data):
            self.data = data

    class WorkflowStatusEvent:
        def __init__(self, state):
            self.state = state

    agent_framework.ChatMessage = ChatMessage
    agent_framework.AgentExecutorRequest = AgentExecutorRequest
    agent_framework.WorkflowOutputEvent = WorkflowOutputEvent
    agent_framework.WorkflowStatusEvent = WorkflowStatusEvent
    sys.modules["agent_framework"] = agent_framework

    mcp_module = types.ModuleType("mcp")
    mcp_server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")

    class FastMCP:
        def __init__(self, _name: str):
            self.name = _name

        def tool(self):
            def _decorator(fn):
                return fn

            return _decorator

        def run(self, transport: str = "stdio") -> None:
            _ = transport

    fastmcp_module.FastMCP = FastMCP
    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = mcp_server_module
    sys.modules["mcp.server.fastmcp"] = fastmcp_module

    orchestrator = types.ModuleType("orchestrator")
    orchestrator.DEFAULT_ARCHITECT_MODEL = "architect-model"
    orchestrator.DEFAULT_DEVELOPER_MODEL = "developer-model"
    orchestrator.DEFAULT_QA_MODEL = "qa-model"

    fake_llm = FakeLLMClient()

    def _make_fake_executor(default_name: str):
        class _FakeExecutor:
            def __init__(self, *_args, **_kwargs):
                agent_id = str(_kwargs.get("id", default_name))
                self.agent = fake_llm.create_agent(
                    name=agent_id,
                    instructions=f"Stub instructions for {default_name}",
                )

        return _FakeExecutor

    def _create_orchestrator_workflow():
        class _Workflow:
            async def run_stream(self, _messages):
                yield WorkflowOutputEvent("legacy-output")
                yield WorkflowStatusEvent("legacy-complete")

        return _Workflow()

    orchestrator.DeveloperAgent = _make_fake_executor("DeveloperAgent")
    orchestrator.PrincipalArchitect = _make_fake_executor("PrincipalArchitect")
    orchestrator.QualityAssuranceAgent = _make_fake_executor("QualityAssuranceAgent")
    orchestrator.create_ai_client = lambda *_args, **_kwargs: object()
    orchestrator.create_orchestrator_workflow = _create_orchestrator_workflow
    orchestrator.get_base_deployment_name = lambda: "base-model"
    orchestrator.get_credential_for_endpoint = lambda _endpoint: None
    orchestrator.get_project_endpoint = lambda: "https://example.test"
    orchestrator.resolve_deployment_name = lambda _name, default, _base: default
    orchestrator.fake_llm = fake_llm
    sys.modules["orchestrator"] = orchestrator

    autonomous = types.ModuleType("autonomous_orchestrator")
    autonomous.DEFAULT_PLANNER_MODEL = "planner-model"
    autonomous.DEFAULT_EVALUATOR_MODEL = "evaluator-model"
    autonomous.DEFAULT_RESEARCHER_MODEL = "researcher-model"
    autonomous.DEFAULT_VERIFIER_MODEL = "verifier-model"

    class _MemorySystem:
        def __init__(self):
            self.memories = []

    def _create_autonomous_workflow(execution_order=None):
        _ = execution_order

        class _Workflow:
            async def run_stream(self, _messages):
                yield WorkflowOutputEvent("▶ Phase: PLAN")
                yield WorkflowStatusEvent("COMPLETE")

        return _Workflow()

    autonomous.MemorySystem = _MemorySystem
    autonomous.create_autonomous_workflow = _create_autonomous_workflow
    sys.modules["autonomous_orchestrator"] = autonomous


def _load_mcp_server_module():
    _install_mcp_server_stubs()
    sys.modules.pop("mcp_server", None)
    return importlib.import_module("mcp_server")


class _FakePlanning:
    def __init__(
        self,
        *,
        mode: str = "design",
        fallback_required: bool = False,
        fallback_reasons: list[str] | None = None,
        execution_order: list[str] | None = None,
    ):
        self.team_spec = SimpleNamespace(
            mode=mode,
            fallback_required=fallback_required,
            fallback_reasons=fallback_reasons or [],
        )
        self.dag_plan = SimpleNamespace(execution_order=execution_order or ["planner", "developer"])

    def to_dict(self):
        return {
            "requested_mode": "auto",
            "resolved_mode": self.team_spec.mode,
            "team_spec": {
                "mode": self.team_spec.mode,
                "fallback_required": self.team_spec.fallback_required,
                "fallback_reasons": list(self.team_spec.fallback_reasons),
                "assignments": [],
            },
            "dag_plan": {
                "execution_order": list(self.dag_plan.execution_order),
                "nodes": [],
            },
            "discovered_skills": [],
            "classified_skills": [],
            "task": "test",
        }


def test_dynamic_plan_preview_contract_shape():
    mcp_server = _load_mcp_server_module()

    payload = mcp_server.dynamic_plan_preview("Implement secure endpoint", mode="auto")

    assert "task" in payload
    assert "requested_mode" in payload
    assert "resolved_mode" in payload
    assert "team_spec" in payload
    assert "dag_plan" in payload
    assert isinstance(payload["dag_plan"]["execution_order"], list)


def test_autonomous_execute_returns_loop_history_and_no_fallback_by_default():
    mcp_server = _load_mcp_server_module()

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Implement endpoint with tests",
            mode="auto",
            max_loops=2,
            enable_legacy_fallback=False,
        )
    )

    assert result["loops_requested"] == 2
    assert result["loops_requested_raw"] == 2
    assert result["loops_clamped"] is False
    assert result["loops_executed"] >= 1
    assert isinstance(result["loop_history"], list)
    assert isinstance(result["correlation_id"], str)
    assert result["correlation_id"]
    assert "telemetry" in result
    assert result["telemetry"]["fallback_rate"] == 0.0
    assert "discovery_success_rate" in result["telemetry"]
    assert "classification_confidence" in result["telemetry"]
    assert "dag_latency_ms" in result["telemetry"]
    assert "loop_metrics" in result["telemetry"]
    assert isinstance(result["telemetry"]["loop_metrics"], list)
    assert result["fallback"]["triggered"] is False


def test_autonomous_execute_emits_structured_logs_with_correlation_and_phase(caplog):
    mcp_server = _load_mcp_server_module()

    with caplog.at_level(logging.INFO, logger="mcp_server"):
        result = asyncio.run(
            mcp_server.autonomous_execute(
                "Implement endpoint with tests",
                mode="auto",
                max_loops=1,
                enable_legacy_fallback=False,
            )
        )

    prefix = "[Autonomous][Structured] "
    payloads = []
    for record in caplog.records:
        message = record.getMessage()
        if not message.startswith(prefix):
            continue
        payloads.append(json.loads(message[len(prefix):]))

    assert payloads
    assert any(item["event"] == "autonomous.start" for item in payloads)
    assert any(item["event"] == "planning.completed" for item in payloads)
    assert any(item["event"] == "phase.transition" for item in payloads)
    assert any(item["event"] == "autonomous.completed" for item in payloads)

    correlation_id = result["correlation_id"]
    assert all(item.get("correlation_id") == correlation_id for item in payloads)


def test_autonomous_execute_translates_legacy_setting_aliases(monkeypatch):
    mcp_server = _load_mcp_server_module()

    monkeypatch.setattr(
        mcp_server,
        "build_dynamic_planning_result",
        lambda **_kwargs: _FakePlanning(mode="fix_bug", fallback_required=False),
    )

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Fix regression in auth flow",
            mode="bugfix",
            execution_mode="hybrid",
            max_loops=1,
            enable_legacy_fallback="true",
        )
    )

    assert result["effective_mode"] == "fix_bug"
    assert result["fallback"]["triggered"] is False


def test_dynamic_plan_preview_rejects_invalid_mode():
    mcp_server = _load_mcp_server_module()

    with pytest.raises(ValueError, match="Invalid mode"):
        mcp_server.dynamic_plan_preview("Implement endpoint", mode="unsupported")


def test_autonomous_execute_rejects_invalid_execution_mode():
    mcp_server = _load_mcp_server_module()

    with pytest.raises(ValueError, match="Invalid execution_mode"):
        asyncio.run(
            mcp_server.autonomous_execute(
                "Implement endpoint",
                mode="implement",
                execution_mode="unsupported",
                max_loops=1,
                enable_legacy_fallback=True,
            )
        )


@pytest.mark.parametrize(
    "execution_mode,mode,expected_effective_mode",
    [
        ("legacy", "implement", "legacy"),
        ("dynamic", "design", "design"),
        ("auto", "debug", "debug"),
    ],
)
def test_autonomous_execute_execution_mode_matrix(
    monkeypatch,
    execution_mode,
    mode,
    expected_effective_mode,
):
    mcp_server = _load_mcp_server_module()

    monkeypatch.setattr(
        mcp_server,
        "build_dynamic_planning_result",
        lambda **_kwargs: _FakePlanning(mode=mode, fallback_required=False),
    )

    result = asyncio.run(
        mcp_server.autonomous_execute(
            f"Run representative {mode} task",
            mode=mode,
            execution_mode=execution_mode,
            max_loops=1,
            enable_legacy_fallback=True,
        )
    )

    assert result["effective_mode"] == expected_effective_mode
    assert result["loops_requested"] == 1
    assert result["loops_executed"] == 1

    if execution_mode == "legacy":
        assert result["fallback"]["triggered"] is False
        assert result["fallback"]["mode_used"] == "legacy"
        assert result["final_status"] == "legacy-complete"
    else:
        assert result["fallback"]["triggered"] is False
        assert result["success_indicators"]["completed"] is True


def test_autonomous_execute_clamps_loop_count_to_minimum(monkeypatch):
    mcp_server = _load_mcp_server_module()

    async def _incomplete_run(_task_prompt: str, execution_order=None):
        _ = execution_order
        return {
            "phases_executed": ["PLAN"],
            "final_status": "INCOMPLETE",
            "iteration_count": 1,
            "outputs": ["still working"],
            "success_indicators": {"completed": False, "verified": False},
        }

    monkeypatch.setattr(mcp_server, "_collect_autonomous_run", _incomplete_run)

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Implement endpoint with tests",
            mode="implement",
            max_loops=0,
            enable_legacy_fallback=False,
        )
    )

    assert result["loops_requested"] == 1
    assert result["loops_requested_raw"] == 0
    assert result["loops_clamped"] is True
    assert result["loops_executed"] == 1


def test_autonomous_execute_clamps_loop_count_to_maximum(monkeypatch):
    mcp_server = _load_mcp_server_module()

    async def _incomplete_run(_task_prompt: str, execution_order=None):
        _ = execution_order
        return {
            "phases_executed": ["PLAN"],
            "final_status": "INCOMPLETE",
            "iteration_count": 1,
            "outputs": ["still working"],
            "success_indicators": {"completed": False, "verified": False},
        }

    monkeypatch.setattr(mcp_server, "_collect_autonomous_run", _incomplete_run)

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Implement endpoint with tests",
            mode="implement",
            max_loops=999,
            enable_legacy_fallback=False,
        )
    )

    assert result["loops_requested"] == 5
    assert result["loops_requested_raw"] == 999
    assert result["loops_clamped"] is True
    assert result["loops_executed"] == 5


@pytest.mark.parametrize("mode", ["design", "fix_bug", "debug", "implement", "refactor"])
def test_autonomous_execute_dynamic_mode_matrix_success(mode):
    mcp_server = _load_mcp_server_module()

    result = asyncio.run(
        mcp_server.autonomous_execute(
            f"Run representative {mode} task",
            mode=mode,
            max_loops=1,
            enable_legacy_fallback=False,
        )
    )

    assert result["effective_mode"] == mode
    assert result["loops_requested"] == 1
    assert result["loops_executed"] == 1
    assert result["success_indicators"]["completed"] is True
    assert result["fallback"]["triggered"] is False


def test_autonomous_execute_falls_back_when_planning_requires_fallback(monkeypatch):
    mcp_server = _load_mcp_server_module()

    monkeypatch.setattr(
        mcp_server,
        "build_dynamic_planning_result",
        lambda **_kwargs: _FakePlanning(
            mode="design",
            fallback_required=True,
            fallback_reasons=["Missing capability 'architecture'."],
        ),
    )

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Design auth service",
            mode="auto",
            execution_mode="auto",
            max_loops=1,
            enable_legacy_fallback=True,
        )
    )

    assert result["effective_mode"] == "legacy"
    assert result["fallback"]["triggered"] is True
    assert result["fallback"]["mode_used"] == "legacy"
    assert result["fallback"]["diagnostics"]["branch"] == "planning"
    assert result["fallback"]["diagnostics"]["execution_mode"] == "auto"
    assert result["final_status"] == "legacy-complete"


def test_autonomous_execute_dynamic_mode_no_fallback_when_planning_requires_fallback(monkeypatch):
    mcp_server = _load_mcp_server_module()

    monkeypatch.setattr(
        mcp_server,
        "build_dynamic_planning_result",
        lambda **_kwargs: _FakePlanning(
            mode="design",
            fallback_required=True,
            fallback_reasons=["Missing capability 'architecture'."],
        ),
    )

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Design auth service",
            mode="auto",
            execution_mode="dynamic",
            max_loops=1,
            enable_legacy_fallback=True,
        )
    )

    assert result["effective_mode"] == "design"
    assert result["fallback"]["triggered"] is False
    assert result["final_status"] == "COMPLETE"


def test_autonomous_execute_invalid_execution_order_without_fallback_returns_dynamic_error(monkeypatch):
    mcp_server = _load_mcp_server_module()

    monkeypatch.setattr(
        mcp_server,
        "build_dynamic_planning_result",
        lambda **_kwargs: _FakePlanning(
            mode="design",
            fallback_required=False,
            execution_order=["unsupported-role"],
        ),
    )

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Design auth service",
            mode="auto",
            execution_mode="dynamic",
            max_loops=1,
            enable_legacy_fallback=True,
        )
    )

    assert result["fallback"]["triggered"] is False
    assert result["final_status"].startswith("dynamic_error:")
    assert "execution_order invalid" in result["final_status"]
    assert result["telemetry"]["execution_order_valid_ratio"] == 0.0
    assert result["loop_history"][0]["telemetry"]["execution_order_valid_ratio"] == 0.0


def test_autonomous_execute_invalid_execution_order_with_fallback_uses_legacy(monkeypatch):
    mcp_server = _load_mcp_server_module()

    monkeypatch.setattr(
        mcp_server,
        "build_dynamic_planning_result",
        lambda **_kwargs: _FakePlanning(
            mode="design",
            fallback_required=False,
            execution_order=["unsupported-role"],
        ),
    )

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Design auth service",
            mode="auto",
            execution_mode="auto",
            max_loops=1,
            enable_legacy_fallback=True,
        )
    )

    assert result["effective_mode"] == "legacy"
    assert result["fallback"]["triggered"] is True
    assert result["fallback"]["diagnostics"]["branch"] == "planning"
    assert "no valid roles" in result["fallback"]["reason"].lower()
    assert result["final_status"] == "legacy-complete"


def test_autonomous_execute_falls_back_on_runtime_exception(monkeypatch):
    mcp_server = _load_mcp_server_module()

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("workflow exploded")

    monkeypatch.setattr(mcp_server, "_collect_autonomous_run", _raise)

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Implement auth endpoint",
            mode="implement",
            execution_mode="auto",
            max_loops=1,
            enable_legacy_fallback=True,
        )
    )

    assert result["fallback"]["triggered"] is True
    assert result["fallback"]["mode_used"] == "legacy"
    assert result["fallback"]["diagnostics"]["branch"] == "runtime"
    assert result["fallback"]["diagnostics"]["execution_mode"] == "auto"
    assert "dynamic runtime failure" in result["fallback"]["reason"]


def test_autonomous_execute_dynamic_mode_runtime_exception_no_fallback(monkeypatch):
    mcp_server = _load_mcp_server_module()

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("workflow exploded")

    monkeypatch.setattr(mcp_server, "_collect_autonomous_run", _raise)

    result = asyncio.run(
        mcp_server.autonomous_execute(
            "Implement auth endpoint",
            mode="implement",
            execution_mode="dynamic",
            max_loops=1,
            enable_legacy_fallback=True,
        )
    )

    assert result["fallback"]["triggered"] is False
    assert result["final_status"].startswith("dynamic_error:")


@pytest.mark.parametrize("case", GOLDEN_ROUTING_FALLBACK_CASES, ids=golden_case_ids(GOLDEN_ROUTING_FALLBACK_CASES))
def test_autonomous_execute_matches_golden_routing_and_fallback_contract(monkeypatch, case):
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
            raise TimeoutError("golden timeout")
        return {
            "phases_executed": ["PLAN", "EXECUTE", "VERIFY"],
            "final_status": case["run_final_status"],
            "iteration_count": 1,
            "outputs": [f"golden:{case['id']}"],
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

    if case["expected_fallback_triggered"]:
        assert result["final_status"] == "legacy-complete"
    elif case["run_should_raise"]:
        assert result["final_status"].startswith("dynamic_error:")
    else:
        assert result["final_status"] == case["run_final_status"]


def test_specialized_mcp_tools_exercise_fake_llm_client():
    mcp_server = _load_mcp_server_module()

    architect_output = asyncio.run(
        mcp_server.architect_design("Design deterministic auth module")
    )
    developer_output = asyncio.run(
        mcp_server.developer_implement(
            "Implement deterministic auth module",
            architecture="{\"layers\": [\"api\", \"service\"]}",
        )
    )
    qa_output = asyncio.run(
        mcp_server.qa_review("Must be deterministic", "Implementation summary")
    )

    suite = mcp_server.get_executor_suite()

    assert "architect_mcp" in architect_output
    assert "developer_mcp" in developer_output
    assert "qa_mcp" in qa_output
    assert len(suite.architect.agent.calls) >= 1
    assert len(suite.developer.agent.calls) >= 1
    assert len(suite.qa.agent.calls) >= 1
