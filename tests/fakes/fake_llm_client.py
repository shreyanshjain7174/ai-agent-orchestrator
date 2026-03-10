from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeLLMAgent:
    """Deterministic async LLM agent used in offline tests."""

    name: str
    instructions: str
    scripted_responses: list[str] = field(default_factory=list)
    default_response: str = ""
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def run(self, messages: list[Any], should_respond: bool = True) -> Any:
        self.calls.append(
            {
                "message_count": len(messages),
                "should_respond": should_respond,
            }
        )

        if self.scripted_responses:
            text = self.scripted_responses.pop(0)
        else:
            text = self.default_response or f'{{"agent":"{self.name}","status":"ok"}}'

        return SimpleNamespace(text=text)


@dataclass
class FakeLLMClient:
    """Deterministic fake client matching the create_agent contract."""

    responses_by_agent: dict[str, list[str]] = field(default_factory=dict)
    default_responses_by_agent: dict[str, str] = field(default_factory=dict)
    created_agents: dict[str, FakeLLMAgent] = field(default_factory=dict)

    def create_agent(self, name: str, instructions: str) -> FakeLLMAgent:
        responses = list(self.responses_by_agent.get(name, []))
        default_response = self.default_responses_by_agent.get(
            name,
            f'{{"agent":"{name}","status":"ok"}}',
        )
        agent = FakeLLMAgent(
            name=name,
            instructions=instructions,
            scripted_responses=responses,
            default_response=default_response,
        )
        self.created_agents[name] = agent
        return agent
