from __future__ import annotations

from dataclasses import dataclass

from dynamic_orchestration import Capability, TaskProfile, TeamAssignment, TeamSpec


@dataclass
class FakeTeamComposer:
    """Predictable team composer for integration and failure-mode tests."""

    force_mode: str = "implement"

    def compose(self, profile: TaskProfile, classified: list) -> TeamSpec:
        assignments: list[TeamAssignment] = []
        for item in classified:
            capability = item.capabilities[0]
            assignments.append(
                TeamAssignment(
                    role=f"role-{capability.value}",
                    capability=capability,
                    skill_id=item.skill.id,
                    confidence=item.confidence_by_capability.get(capability, 0.9),
                )
            )

        return TeamSpec(
            mode=self.force_mode if profile.mode == "auto" else profile.mode,
            assignments=assignments,
            fallback_required=not assignments,
            fallback_reasons=[] if assignments else ["No assignments could be built."],
        )
