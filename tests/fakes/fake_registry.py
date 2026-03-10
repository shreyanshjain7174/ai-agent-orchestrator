from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from dynamic_orchestration import SkillMetadata, SkillRegistry


@dataclass
class FakeSkillRegistry(SkillRegistry):
    """In-memory deterministic skill registry used in tests."""

    skills: tuple[SkillMetadata, ...]

    def discover(self) -> list[SkillMetadata]:
        return list(self.skills)


def build_registry_from_tuples(items: Iterable[tuple[str, str, str]]) -> FakeSkillRegistry:
    """Quick helper to build fake registry data from tuples."""
    skills = tuple(
        SkillMetadata(id=skill_id, name=name, description=description, source="fake")
        for skill_id, name, description in items
    )
    return FakeSkillRegistry(skills=skills)
