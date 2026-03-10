"""Deterministic fake components for architecture tests."""

from .fake_classifier import FakeSkillClassifier
from .fake_dag_executor import FakeDagExecutor
from .fake_llm_client import FakeLLMClient, FakeLLMAgent
from .fake_memory_store import FakeMemoryStore
from .fake_registry import FakeSkillRegistry, build_registry_from_tuples
from .fake_team_composer import FakeTeamComposer

__all__ = [
    "FakeDagExecutor",
    "FakeLLMClient",
    "FakeLLMAgent",
    "FakeMemoryStore",
    "FakeSkillClassifier",
    "FakeSkillRegistry",
    "FakeTeamComposer",
    "build_registry_from_tuples",
]
