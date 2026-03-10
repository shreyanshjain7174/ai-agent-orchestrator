# pyright: reportMissingImports=false

from dynamic_orchestration import (
    Capability,
    ClassifiedSkill,
    SkillMetadata,
    TaskProfile,
    TeamComposer,
)


def _classified(capability: Capability, confidence: float = 0.9) -> ClassifiedSkill:
    return ClassifiedSkill(
        skill=SkillMetadata(
            id=f"{capability.value}-skill",
            name=f"{capability.value.title()} Skill",
            description=f"Handles {capability.value}",
            health="healthy",
        ),
        capabilities=(capability,),
        confidence_by_capability={capability: confidence},
    )


def test_team_composer_enforces_max_team_size_with_critical_precedence():
    composer = TeamComposer(max_team_size=3)
    pool = [
        _classified(Capability.PLANNING),
        _classified(Capability.IMPLEMENTATION),
        _classified(Capability.VERIFICATION),
        _classified(Capability.SECURITY),
        _classified(Capability.TESTING),
    ]

    first = composer.compose(
        TaskProfile(task="Implement secure auth endpoint with tests", mode="implement"),
        pool,
    )
    second = composer.compose(
        TaskProfile(task="Implement secure auth endpoint with tests", mode="implement"),
        pool,
    )

    first_caps = {assignment.capability for assignment in first.assignments}
    assert len(first.assignments) == 3
    assert Capability.PLANNING in first_caps
    assert Capability.IMPLEMENTATION in first_caps
    assert Capability.VERIFICATION in first_caps
    assert first.assignments == second.assignments


def test_team_composer_flags_missing_critical_capability():
    composer = TeamComposer(max_team_size=6)
    pool = [
        _classified(Capability.PLANNING),
        _classified(Capability.VERIFICATION),
    ]

    spec = composer.compose(
        TaskProfile(task="Implement API endpoint", mode="implement"),
        pool,
    )

    assert spec.fallback_required is True
    assert any("Critical capability 'implementation'" in reason for reason in spec.fallback_reasons)


def test_team_composer_reports_when_critical_assignments_exceed_bound():
    composer = TeamComposer(max_team_size=2)
    pool = [
        _classified(Capability.PLANNING, 0.99),
        _classified(Capability.IMPLEMENTATION, 0.98),
        _classified(Capability.VERIFICATION, 0.97),
    ]

    spec = composer.compose(
        TaskProfile(task="Implement endpoint", mode="implement"),
        pool,
    )

    assert len(spec.assignments) == 2
    assert spec.fallback_required is True
    assert any("max_team_size=2" in reason for reason in spec.fallback_reasons)
