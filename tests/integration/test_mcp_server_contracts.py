# pyright: reportMissingImports=false

import asyncio
import importlib
import sys
import types
from types import SimpleNamespace

import pytest


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

    class _FakeAgent:
        async def run(self, messages, should_respond=True):
            _ = (messages, should_respond)
            return SimpleNamespace(text="ok")

    class _FakeExecutor:
        def __init__(self, *_args, **_kwargs):
            self.agent = _FakeAgent()

    def _create_orchestrator_workflow():
        class _Workflow:
            async def run_stream(self, _messages):
                yield WorkflowOutputEvent("legacy-output")
                yield WorkflowStatusEvent("legacy-complete")

        return _Workflow()

    orchestrator.DeveloperAgent = _FakeExecutor
    orchestrator.PrincipalArchitect = _FakeExecutor
    orchestrator.QualityAssuranceAgent = _FakeExecutor
    orchestrator.create_ai_client = lambda *_args, **_kwargs: object()
    orchestrator.create_orchestrator_workflow = _create_orchestrator_workflow
    orchestrator.get_base_deployment_name = lambda: "base-model"
    orchestrator.get_credential_for_endpoint = lambda _endpoint: None
    orchestrator.get_project_endpoint = lambda: "https://example.test"
    orchestrator.resolve_deployment_name = lambda _name, default, _base: default
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
    assert result["loops_executed"] >= 1
    assert isinstance(result["loop_history"], list)
    assert result["fallback"]["triggered"] is False


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
