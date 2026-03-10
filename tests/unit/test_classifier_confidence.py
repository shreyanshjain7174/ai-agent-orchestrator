# pyright: reportMissingImports=false

from dynamic_orchestration import Capability, RuleBasedSkillClassifier, SkillMetadata


def test_classifier_handles_clear_cut_security_fixture():
    classifier = RuleBasedSkillClassifier()
    skill = SkillMetadata(
        id="security-auditor",
        name="Security Auditor",
        description="Performs security vulnerability review and auth threat analysis.",
        tags=("security", "audit"),
    )

    classified = classifier.classify([skill])[0]

    assert classified.capabilities[0] == Capability.SECURITY
    assert classified.confidence_by_capability[Capability.SECURITY] >= 0.6


def test_classifier_handles_ambiguous_fixture_deterministically():
    classifier = RuleBasedSkillClassifier()
    skill = SkillMetadata(
        id="architect-dev-hybrid",
        name="Architect Developer Hybrid",
        description="Design architecture and implement code with scalable system interfaces.",
        tags=("architecture", "implementation"),
    )

    classified = classifier.classify([skill])[0]

    assert Capability.ARCHITECTURE in classified.capabilities
    assert Capability.IMPLEMENTATION in classified.capabilities
    assert classified.capabilities[0] == Capability.ARCHITECTURE
    assert (
        classified.confidence_by_capability[Capability.ARCHITECTURE]
        > classified.confidence_by_capability[Capability.IMPLEMENTATION]
    )


def test_classifier_threshold_is_configurable():
    strict_classifier = RuleBasedSkillClassifier(min_confidence=0.8)
    weak_signal_skill = SkillMetadata(
        id="single-keyword",
        name="Single Keyword",
        description="Handles security concerns.",
        tags=(),
    )

    classified = strict_classifier.classify([weak_signal_skill])[0]

    assert classified.capabilities == (Capability.UNKNOWN,)
    assert classified.confidence_by_capability[Capability.UNKNOWN] >= 0.6
