from __future__ import annotations

from dataclasses import dataclass

from dynamic_orchestration import Capability, ClassifiedSkill, SkillMetadata


@dataclass
class FakeSkillClassifier:
    """Predictable classifier returning pre-mapped capabilities by skill id."""

    mapping: dict[str, tuple[Capability, ...]]

    def classify(self, skills: list[SkillMetadata]) -> list[ClassifiedSkill]:
        classified: list[ClassifiedSkill] = []
        for skill in skills:
            capabilities = self.mapping.get(skill.id, (Capability.UNKNOWN,))
            confidence = {cap: 0.9 for cap in capabilities}
            classified.append(
                ClassifiedSkill(
                    skill=skill,
                    capabilities=capabilities,
                    confidence_by_capability=confidence,
                )
            )
        return classified
