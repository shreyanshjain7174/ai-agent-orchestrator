"""Dynamic orchestration foundation for reusable multi-project execution.

This module provides the Phase 1-4 core abstractions:
- Skill discovery via pluggable registries
- Capability classification with deterministic rules
- Dynamic team composition by task/mode
- Adaptive DAG planning with cycle-safe execution order

It is intentionally pure-Python and side-effect light so it can be reused in
other projects and tested without LLM or MCP network calls.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Iterable, Protocol


logger = logging.getLogger(__name__)


_LEGACY_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "AI_ORCHESTRATOR_SKILLS_JSON": ("ORCHESTRATOR_SKILLS_JSON", "SKILLS_JSON"),
    "AI_ORCHESTRATOR_ENABLE_SKILL_DISCOVERY": (
        "ORCHESTRATOR_ENABLE_SKILL_DISCOVERY",
        "ENABLE_SKILL_DISCOVERY",
    ),
    "AI_ORCHESTRATOR_DISCOVERY_RETRY_ATTEMPTS": (
        "ORCHESTRATOR_DISCOVERY_RETRY_ATTEMPTS",
        "DISCOVERY_RETRY_ATTEMPTS",
    ),
    "AI_ORCHESTRATOR_DISCOVERY_TTL_SECONDS": (
        "ORCHESTRATOR_DISCOVERY_TTL_SECONDS",
        "DISCOVERY_TTL_SECONDS",
    ),
    "AI_ORCHESTRATOR_CLASSIFIER_MIN_CONFIDENCE": (
        "ORCHESTRATOR_CLASSIFIER_MIN_CONFIDENCE",
        "CLASSIFIER_MIN_CONFIDENCE",
    ),
    "AI_ORCHESTRATOR_MAX_TEAM_SIZE": ("ORCHESTRATOR_MAX_TEAM_SIZE", "MAX_TEAM_SIZE"),
    "AI_ORCHESTRATOR_DAG_MODE": ("ORCHESTRATOR_DAG_MODE", "DAG_MODE"),
    "AI_ORCHESTRATOR_MAX_DAG_NODES": ("ORCHESTRATOR_MAX_DAG_NODES", "MAX_DAG_NODES"),
}

_TRUE_BOOL_VALUES = {"1", "true", "yes", "on"}
_FALSE_BOOL_VALUES = {"0", "false", "no", "off"}


class Capability(str, Enum):
    """Capability taxonomy used by dynamic orchestration policies."""

    PLANNING = "planning"
    EVALUATION = "evaluation"
    RESEARCH = "research"
    ARCHITECTURE = "architecture"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    ORCHESTRATION = "orchestration"
    SECURITY = "security"
    TESTING = "testing"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SkillMetadata:
    """Normalized skill metadata produced by registries."""

    id: str
    name: str
    description: str
    source: str = "builtin"
    tags: tuple[str, ...] = ()
    input_schema_summary: str = ""
    health: str = "unknown"


@dataclass(frozen=True)
class ClassifiedSkill:
    """Skill with one or more mapped capabilities and confidence scores."""

    skill: SkillMetadata
    capabilities: tuple[Capability, ...]
    confidence_by_capability: dict[Capability, float]


@dataclass(frozen=True)
class TaskProfile:
    """Task inputs used for dynamic team composition."""

    task: str
    mode: str = "auto"
    constraints: str = ""


@dataclass(frozen=True)
class TeamAssignment:
    """Selected skill assignment for a specific role/capability."""

    role: str
    capability: Capability
    skill_id: str
    confidence: float


@dataclass
class TeamSpec:
    """Team composition result for a task profile."""

    mode: str
    assignments: list[TeamAssignment] = field(default_factory=list)
    fallback_required: bool = False
    fallback_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DagNode:
    """Single execution node in an adaptive DAG."""

    id: str
    role: str
    skill_id: str
    depends_on: tuple[str, ...] = ()


@dataclass
class DagPlan:
    """Validated DAG plus computed topological execution order."""

    nodes: list[DagNode]
    execution_order: list[str]


@dataclass
class DynamicPlanningResult:
    """Full dynamic planning result that can be emitted by APIs/tools."""

    task: str
    requested_mode: str
    discovered_skills: list[SkillMetadata]
    classified_skills: list[ClassifiedSkill]
    team_spec: TeamSpec
    dag_plan: DagPlan

    def to_dict(self) -> dict:
        """Serialize to plain dict for JSON-safe API responses."""

        return {
            "task": self.task,
            "requested_mode": self.requested_mode,
            "resolved_mode": self.team_spec.mode,
            "discovered_skills": [
                {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "source": skill.source,
                    "tags": list(skill.tags),
                    "input_schema_summary": skill.input_schema_summary,
                    "health": skill.health,
                }
                for skill in self.discovered_skills
            ],
            "classified_skills": [
                {
                    "id": item.skill.id,
                    "name": item.skill.name,
                    "capabilities": [cap.value for cap in item.capabilities],
                    "confidence": {
                        cap.value: score for cap, score in item.confidence_by_capability.items()
                    },
                }
                for item in self.classified_skills
            ],
            "team_spec": {
                "mode": self.team_spec.mode,
                "fallback_required": self.team_spec.fallback_required,
                "fallback_reasons": self.team_spec.fallback_reasons,
                "assignments": [
                    {
                        "role": assignment.role,
                        "capability": assignment.capability.value,
                        "skill_id": assignment.skill_id,
                        "confidence": assignment.confidence,
                    }
                    for assignment in self.team_spec.assignments
                ],
            },
            "dag_plan": {
                "nodes": [
                    {
                        "id": node.id,
                        "role": node.role,
                        "skill_id": node.skill_id,
                        "depends_on": list(node.depends_on),
                    }
                    for node in self.dag_plan.nodes
                ],
                "execution_order": self.dag_plan.execution_order,
            },
        }


class SkillRegistry(Protocol):
    """Protocol for skill inventory providers."""

    def discover(self) -> list[SkillMetadata]:
        """Return available skills with normalized metadata."""


_VALID_HEALTH_VALUES = {"healthy", "degraded", "unknown", "unhealthy"}


def normalize_skill_metadata(skill: SkillMetadata) -> SkillMetadata:
    """Normalize discovery output into a stable, deterministic schema."""

    normalized_tags = tuple(
        tag.strip().lower()
        for tag in skill.tags
        if str(tag).strip()
    )
    normalized_health = skill.health.strip().lower() if skill.health else "unknown"
    if normalized_health not in _VALID_HEALTH_VALUES:
        normalized_health = "unknown"

    return SkillMetadata(
        id=skill.id.strip(),
        name=skill.name.strip(),
        description=skill.description.strip(),
        source=(skill.source or "unknown").strip().lower(),
        tags=normalized_tags,
        input_schema_summary=skill.input_schema_summary.strip(),
        health=normalized_health,
    )


@dataclass
class DiscoveryCacheEntry:
    """In-memory cache entry for discovered inventory snapshots."""

    skills: list[SkillMetadata]
    refreshed_at: float


class CachedSkillRegistry:
    """Cache wrapper with retry and stale-result fallback for discovery."""

    def __init__(
        self,
        registry: SkillRegistry,
        ttl_seconds: float = 60.0,
        retry_attempts: int = 1,
        now_fn: Callable[[], float] | None = None,
    ):
        self.registry = registry
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.retry_attempts = max(0, int(retry_attempts))
        self._now_fn = now_fn or time.monotonic
        self._cache: DiscoveryCacheEntry | None = None

    def discover(self) -> list[SkillMetadata]:
        if self._cache and not self._is_stale(self._cache):
            return list(self._cache.skills)

        try:
            refreshed = self._discover_with_retry()
        except Exception:
            if self._cache:
                # Surface stale inventory but mark it degraded for callers.
                return [replace(skill, health="degraded") for skill in self._cache.skills]
            return []

        self._cache = DiscoveryCacheEntry(skills=refreshed, refreshed_at=self._now_fn())
        return list(refreshed)

    def _discover_with_retry(self) -> list[SkillMetadata]:
        last_exc: Exception | None = None
        for _ in range(self.retry_attempts + 1):
            try:
                discovered = self.registry.discover()
                return [normalize_skill_metadata(skill) for skill in discovered]
            except Exception as exc:  # pragma: no cover - exercised through behavior tests
                last_exc = exc
                continue

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Discovery failed with no exception details.")

    def _is_stale(self, entry: DiscoveryCacheEntry) -> bool:
        return (self._now_fn() - entry.refreshed_at) > self.ttl_seconds


class StaticSkillRegistry:
    """Registry backed by a static in-memory list."""

    def __init__(self, skills: Iterable[SkillMetadata]):
        self._skills = list(skills)

    def discover(self) -> list[SkillMetadata]:
        return list(self._skills)


class EnvSkillRegistry:
    """Registry backed by JSON in an environment variable.

    Expected format for AI_ORCHESTRATOR_SKILLS_JSON:
    [
      {
        "id": "python-pro",
        "name": "Python Pro",
        "description": "Expert Python implementation",
        "source": "env",
        "tags": ["python", "implementation"],
        "health": "healthy"
      }
    ]
    """

    def __init__(self, env_var: str = "AI_ORCHESTRATOR_SKILLS_JSON"):
        self.env_var = env_var

    def discover(self) -> list[SkillMetadata]:
        raw = (_env_raw(self.env_var) or "").strip()
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        if not isinstance(data, list):
            return []

        discovered: list[SkillMetadata] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            skill_id = str(item.get("id", "")).strip()
            name = str(item.get("name", "")).strip()
            description = str(item.get("description", "")).strip()
            if not skill_id or not name or not description:
                continue

            tags_raw = item.get("tags", [])
            tags: tuple[str, ...]
            if isinstance(tags_raw, list):
                tags = tuple(str(t).strip().lower() for t in tags_raw if str(t).strip())
            else:
                tags = ()

            discovered.append(
                normalize_skill_metadata(SkillMetadata(
                    id=skill_id,
                    name=name,
                    description=description,
                    source=str(item.get("source", "env")),
                    tags=tags,
                    input_schema_summary=str(item.get("input_schema_summary", "")),
                    health=str(item.get("health", "unknown")),
                ))
            )
        return discovered


class CompositeSkillRegistry:
    """Registry that merges multiple registries with first-wins dedupe."""

    def __init__(self, registries: Iterable[SkillRegistry], retry_attempts: int = 0):
        self.registries = list(registries)
        self.retry_attempts = max(0, int(retry_attempts))

    def discover(self) -> list[SkillMetadata]:
        merged: list[SkillMetadata] = []
        seen: set[str] = set()
        for registry in self.registries:
            skills = self._discover_with_retry(registry)
            if not skills:
                continue
            for skill in skills:
                normalized = normalize_skill_metadata(skill)
                if not normalized.id or not normalized.name or not normalized.description:
                    continue
                if normalized.id in seen:
                    continue
                seen.add(normalized.id)
                merged.append(normalized)
        return merged

    def _discover_with_retry(self, registry: SkillRegistry) -> list[SkillMetadata]:
        for attempt in range(self.retry_attempts + 1):
            try:
                return registry.discover()
            except Exception:
                if attempt >= self.retry_attempts:
                    return []
        return []


def default_static_skills() -> list[SkillMetadata]:
    """Built-in baseline skills so orchestration remains functional by default."""

    return [
        SkillMetadata(
            id="planner-agent",
            name="Planner Agent",
            description="Breaks tasks into executable plans and defines success criteria.",
            source="builtin",
            tags=("planning", "task-decomposition"),
            health="healthy",
        ),
        SkillMetadata(
            id="evaluator-agent",
            name="Evaluator Agent",
            description="Evaluates output quality, risks, and loop continuation decisions.",
            source="builtin",
            tags=("evaluation", "quality", "orchestration"),
            health="healthy",
        ),
        SkillMetadata(
            id="researcher-agent",
            name="Researcher Agent",
            description="Gathers context and best-practice references before implementation.",
            source="builtin",
            tags=("research", "context"),
            health="healthy",
        ),
        SkillMetadata(
            id="architect-agent",
            name="Architect Agent",
            description="Designs scalable architecture, interfaces, and implementation guidance.",
            source="builtin",
            tags=("architecture", "design"),
            health="healthy",
        ),
        SkillMetadata(
            id="developer-agent",
            name="Developer Agent",
            description="Implements features, code changes, and deterministic tests.",
            source="builtin",
            tags=("implementation", "coding"),
            health="healthy",
        ),
        SkillMetadata(
            id="verifier-agent",
            name="Verifier Agent",
            description="Verifies quality, testing, and security readiness before completion.",
            source="builtin",
            tags=("verification", "testing", "security"),
            health="healthy",
        ),
    ]


def _env_int(name: str, default: int) -> int:
    value = _env_raw(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = _env_raw(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = _env_raw(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in _TRUE_BOOL_VALUES:
        return True
    if normalized in _FALSE_BOOL_VALUES:
        return False
    return default


def _env_raw(name: str) -> str | None:
    canonical_value = os.getenv(name)
    if canonical_value is not None:
        return canonical_value

    for legacy_name in _LEGACY_ENV_ALIASES.get(name, ()):
        legacy_value = os.getenv(legacy_name)
        if legacy_value is None:
            continue
        logger.warning(
            "[DynamicConfig][DEPRECATION] %s is deprecated; use %s.",
            legacy_name,
            name,
        )
        return legacy_value

    return None


def build_default_registry() -> SkillRegistry:
    """Build production-safe default registry with env overrides and builtins."""

    enable_skill_discovery = _env_bool("AI_ORCHESTRATOR_ENABLE_SKILL_DISCOVERY", True)
    retry_attempts = _env_int("AI_ORCHESTRATOR_DISCOVERY_RETRY_ATTEMPTS", 1)
    ttl_seconds = _env_float("AI_ORCHESTRATOR_DISCOVERY_TTL_SECONDS", 60.0)

    registries: list[SkillRegistry] = []
    if enable_skill_discovery:
        registries.append(EnvSkillRegistry())
    registries.append(StaticSkillRegistry(default_static_skills()))

    composite = CompositeSkillRegistry(
        registries,
        retry_attempts=retry_attempts,
    )
    return CachedSkillRegistry(
        composite,
        ttl_seconds=ttl_seconds,
        retry_attempts=retry_attempts,
    )


class RuleBasedSkillClassifier:
    """Deterministic classifier from skill text to capability tags."""

    _CAPABILITY_KEYWORDS: dict[Capability, tuple[str, ...]] = {
        Capability.PLANNING: ("plan", "planning", "decompose", "roadmap", "spec"),
        Capability.EVALUATION: ("evaluate", "assessment", "review", "score", "audit"),
        Capability.RESEARCH: ("research", "discover", "analyze", "gather", "context"),
        Capability.ARCHITECTURE: ("architecture", "design", "system", "interface", "scalable"),
        Capability.IMPLEMENTATION: ("implement", "code", "build", "develop", "refactor"),
        Capability.VERIFICATION: ("verify", "validation", "qa", "quality", "test"),
        Capability.ORCHESTRATION: ("orchestrate", "workflow", "loop", "coordination"),
        Capability.SECURITY: ("security", "owasp", "vulnerability", "threat", "auth"),
        Capability.TESTING: ("testing", "pytest", "mock", "fixture", "coverage"),
    }

    def __init__(
        self,
        min_confidence: float | None = None,
        base_confidence: float = 0.5,
        keyword_weight: float = 0.1,
        unknown_confidence: float = 0.6,
    ):
        self.min_confidence = self._clamp_confidence(
            min_confidence
            if min_confidence is not None
            else _env_float("AI_ORCHESTRATOR_CLASSIFIER_MIN_CONFIDENCE", 0.6)
        )
        self.base_confidence = self._clamp_confidence(base_confidence)
        self.keyword_weight = max(0.0, float(keyword_weight))
        self.unknown_confidence = self._clamp_confidence(unknown_confidence)

    def classify(self, skills: Iterable[SkillMetadata]) -> list[ClassifiedSkill]:
        """Classify skills with deterministic confidence values."""

        results: list[ClassifiedSkill] = []
        for skill in skills:
            normalized = self._normalize_text(skill)
            confidence: dict[Capability, float] = {}

            for capability, keywords in self._CAPABILITY_KEYWORDS.items():
                score = self._keyword_score(normalized, keywords)
                if score <= 0:
                    continue
                capability_confidence = min(0.99, self.base_confidence + (self.keyword_weight * score))
                if capability_confidence < self.min_confidence:
                    continue
                confidence[capability] = capability_confidence

            if not confidence:
                confidence = {Capability.UNKNOWN: self.unknown_confidence}

            ordered_caps = tuple(
                sorted(confidence.keys(), key=lambda c: confidence[c], reverse=True)
            )
            results.append(
                ClassifiedSkill(
                    skill=skill,
                    capabilities=ordered_caps,
                    confidence_by_capability=confidence,
                )
            )

        return results

    @staticmethod
    def _normalize_text(skill: SkillMetadata) -> str:
        parts = [skill.name, skill.description, " ".join(skill.tags)]
        return " ".join(parts).strip().lower()

    @staticmethod
    def _keyword_score(text: str, keywords: tuple[str, ...]) -> int:
        score = 0
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                score += 1
        return score

    @staticmethod
    def _clamp_confidence(value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class TeamComposer:
    """Composes a capability-aligned team for a task profile."""

    _MODE_REQUIREMENTS: dict[str, tuple[Capability, ...]] = {
        "design": (Capability.PLANNING, Capability.ARCHITECTURE, Capability.VERIFICATION),
        "implement": (Capability.PLANNING, Capability.IMPLEMENTATION, Capability.VERIFICATION),
        "fix_bug": (Capability.EVALUATION, Capability.RESEARCH, Capability.IMPLEMENTATION, Capability.VERIFICATION),
        "debug": (Capability.EVALUATION, Capability.RESEARCH, Capability.IMPLEMENTATION, Capability.VERIFICATION),
        "refactor": (Capability.PLANNING, Capability.ARCHITECTURE, Capability.IMPLEMENTATION, Capability.VERIFICATION),
    }

    _CRITICAL_CAPABILITIES: dict[str, tuple[Capability, ...]] = {
        "design": (Capability.PLANNING, Capability.ARCHITECTURE),
        "implement": (Capability.PLANNING, Capability.IMPLEMENTATION, Capability.VERIFICATION),
        "fix_bug": (Capability.EVALUATION, Capability.IMPLEMENTATION, Capability.VERIFICATION),
        "debug": (Capability.EVALUATION, Capability.IMPLEMENTATION, Capability.VERIFICATION),
        "refactor": (Capability.PLANNING, Capability.IMPLEMENTATION, Capability.VERIFICATION),
    }

    _ROLE_BY_CAPABILITY: dict[Capability, str] = {
        Capability.PLANNING: "planner",
        Capability.EVALUATION: "evaluator",
        Capability.RESEARCH: "researcher",
        Capability.ARCHITECTURE: "architect",
        Capability.IMPLEMENTATION: "developer",
        Capability.VERIFICATION: "verifier",
        Capability.ORCHESTRATION: "orchestrator",
        Capability.SECURITY: "security-reviewer",
        Capability.TESTING: "test-engineer",
        Capability.UNKNOWN: "generalist",
    }

    _OPTIONAL_CAPABILITY_HINTS: tuple[tuple[tuple[str, ...], Capability], ...] = (
        (("security", "secure", "auth", "owasp", "vulnerability"), Capability.SECURITY),
        (("test", "tests", "coverage", "qa", "verify", "verification"), Capability.TESTING),
    )

    def __init__(self, max_team_size: int | None = None):
        resolved_max = (
            _env_int("AI_ORCHESTRATOR_MAX_TEAM_SIZE", 6)
            if max_team_size is None
            else int(max_team_size)
        )
        self.max_team_size = max(1, resolved_max)

    def compose(self, profile: TaskProfile, classified: Iterable[ClassifiedSkill]) -> TeamSpec:
        """Select best skills for required capabilities in the resolved mode."""

        resolved_mode = self._resolve_mode(profile)
        required = self._MODE_REQUIREMENTS.get(resolved_mode, self._MODE_REQUIREMENTS["implement"])
        critical_capabilities = set(
            self._CRITICAL_CAPABILITIES.get(resolved_mode, required)
        )

        optional = self._optional_capabilities_for_task(profile.task)
        target_capabilities = list(required)
        for capability in optional:
            if capability not in target_capabilities:
                target_capabilities.append(capability)

        pool = list(classified)
        assignments: list[TeamAssignment] = []
        fallback_reasons: list[str] = []

        for capability in target_capabilities:
            selected = self._select_best_skill(pool, capability)
            if not selected:
                if capability in critical_capabilities:
                    fallback_reasons.append(
                        f"Critical capability '{capability.value}' missing for mode '{resolved_mode}'."
                    )
                elif capability in required:
                    fallback_reasons.append(
                        f"Missing capability '{capability.value}' for mode '{resolved_mode}'."
                    )
                continue

            confidence = selected.confidence_by_capability.get(capability, 0.0)
            assignments.append(
                TeamAssignment(
                    role=self._ROLE_BY_CAPABILITY[capability],
                    capability=capability,
                    skill_id=selected.skill.id,
                    confidence=confidence,
                )
            )

        assignments, sizing_reason = self._bound_team(assignments, critical_capabilities)
        if sizing_reason:
            fallback_reasons.append(sizing_reason)

        fallback_reasons = self._dedupe_preserve_order(fallback_reasons)

        return TeamSpec(
            mode=resolved_mode,
            assignments=assignments,
            fallback_required=bool(fallback_reasons),
            fallback_reasons=fallback_reasons,
        )

    def _optional_capabilities_for_task(self, task: str) -> tuple[Capability, ...]:
        lowered = task.lower()
        optional: list[Capability] = []
        for keywords, capability in self._OPTIONAL_CAPABILITY_HINTS:
            if any(keyword in lowered for keyword in keywords):
                optional.append(capability)
        return tuple(optional)

    def _bound_team(
        self,
        assignments: list[TeamAssignment],
        critical_capabilities: set[Capability],
    ) -> tuple[list[TeamAssignment], str | None]:
        if len(assignments) <= self.max_team_size:
            return assignments, None

        critical = [a for a in assignments if a.capability in critical_capabilities]
        non_critical = [a for a in assignments if a.capability not in critical_capabilities]

        if len(critical) > self.max_team_size:
            trimmed = sorted(
                critical,
                key=lambda item: (item.confidence, item.role),
                reverse=True,
            )[: self.max_team_size]
            return (
                sorted(trimmed, key=lambda item: item.role),
                f"Critical assignments exceeded max_team_size={self.max_team_size}; trimmed to highest confidence critical roles.",
            )

        remaining_slots = self.max_team_size - len(critical)
        ranked_non_critical = sorted(
            non_critical,
            key=lambda item: (item.confidence, item.role),
            reverse=True,
        )
        bounded = critical + ranked_non_critical[:remaining_slots]
        bounded = sorted(bounded, key=lambda item: item.role)
        return bounded, None

    @staticmethod
    def _dedupe_preserve_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    def _resolve_mode(self, profile: TaskProfile) -> str:
        mode = profile.mode.strip().lower() or "auto"
        if mode != "auto":
            return mode

        task = profile.task.lower()
        if any(keyword in task for keyword in ("bug", "fix", "broken", "error", "regression")):
            return "fix_bug"
        if any(keyword in task for keyword in ("debug", "trace", "diagnose")):
            return "debug"
        if any(keyword in task for keyword in ("refactor", "clean up", "modernize")):
            return "refactor"
        if any(keyword in task for keyword in ("design", "architecture", "proposal")):
            return "design"
        return "implement"

    @staticmethod
    def _select_best_skill(
        classified: Iterable[ClassifiedSkill], capability: Capability
    ) -> ClassifiedSkill | None:
        ranked = [
            item
            for item in classified
            if capability in item.capabilities
        ]
        if not ranked:
            return None
        return sorted(
            ranked,
            key=lambda item: item.confidence_by_capability.get(capability, 0.0),
            reverse=True,
        )[0]


class DagPlanner:
    """Converts TeamSpec into a cycle-safe DAG execution plan."""

    _STATIC_MODE_EDGES: dict[str, tuple[tuple[str, str], ...]] = {
        "design": (("planner", "architect"), ("architect", "verifier")),
        "implement": (("planner", "developer"), ("developer", "verifier")),
        "fix_bug": (("evaluator", "researcher"), ("researcher", "developer"), ("developer", "verifier")),
        "debug": (("evaluator", "researcher"), ("researcher", "developer"), ("developer", "verifier")),
        "refactor": (("planner", "architect"), ("architect", "developer"), ("developer", "verifier")),
    }

    _DYNAMIC_ROLE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
        "planner": (),
        "evaluator": (),
        "researcher": ("evaluator", "planner"),
        "architect": ("planner", "researcher"),
        "developer": ("planner", "architect", "researcher", "evaluator"),
        "security-reviewer": ("architect", "developer"),
        "test-engineer": ("developer",),
        "verifier": ("developer", "architect", "security-reviewer", "test-engineer", "researcher"),
    }

    def __init__(self, dynamic_edges: bool | None = None, max_nodes: int | None = None):
        dag_mode = (_env_raw("AI_ORCHESTRATOR_DAG_MODE") or "dynamic").strip().lower()
        self.dynamic_edges = (
            dag_mode != "static"
            if dynamic_edges is None
            else bool(dynamic_edges)
        )
        resolved_max_nodes = (
            _env_int("AI_ORCHESTRATOR_MAX_DAG_NODES", 24)
            if max_nodes is None
            else int(max_nodes)
        )
        self.max_nodes = max(1, resolved_max_nodes)

    def plan(self, team_spec: TeamSpec) -> DagPlan:
        """Build and validate DAG plan from team assignments."""

        if len(team_spec.assignments) > self.max_nodes:
            raise ValueError(
                f"Team assignment count {len(team_spec.assignments)} exceeds max_nodes={self.max_nodes}."
            )

        node_by_role: dict[str, DagNode] = {}
        for assignment in team_spec.assignments:
            node_by_role[assignment.role] = DagNode(
                id=assignment.role,
                role=assignment.role,
                skill_id=assignment.skill_id,
                depends_on=(),
            )

        if self.dynamic_edges:
            depends_map = self._build_dynamic_dependency_map(node_by_role, team_spec.mode)
        else:
            depends_map = self._build_static_dependency_map(node_by_role, team_spec.mode)

        # If no edges are created (e.g., reduced team), chain deterministically.
        if all(not deps for deps in depends_map.values()) and len(node_by_role) > 1:
            ordered_roles = sorted(node_by_role.keys())
            for idx in range(1, len(ordered_roles)):
                depends_map[ordered_roles[idx]].add(ordered_roles[idx - 1])

        nodes = [
            DagNode(
                id=node.id,
                role=node.role,
                skill_id=node.skill_id,
                depends_on=tuple(sorted(depends_map.get(node.role, set()))),
            )
            for node in node_by_role.values()
        ]

        order = self._topological_sort(nodes)
        return DagPlan(nodes=sorted(nodes, key=lambda n: n.id), execution_order=order)

    def _build_static_dependency_map(
        self,
        node_by_role: dict[str, DagNode],
        mode: str,
    ) -> dict[str, set[str]]:
        edge_template = self._STATIC_MODE_EDGES.get(mode, self._STATIC_MODE_EDGES["implement"])
        depends_map: dict[str, set[str]] = {role: set() for role in node_by_role.keys()}
        for source, target in edge_template:
            if source in node_by_role and target in node_by_role:
                depends_map[target].add(source)
        return depends_map

    def _build_dynamic_dependency_map(
        self,
        node_by_role: dict[str, DagNode],
        mode: str,
    ) -> dict[str, set[str]]:
        depends_map: dict[str, set[str]] = {role: set() for role in node_by_role.keys()}

        for role, dependencies in self._DYNAMIC_ROLE_DEPENDENCIES.items():
            if role not in node_by_role:
                continue
            for dependency in dependencies:
                if dependency in node_by_role and dependency != role:
                    depends_map[role].add(dependency)

        # Mode-aware guardrails to keep legacy execution intent preserved.
        if mode in {"implement", "design", "refactor"}:
            if "planner" in node_by_role and "developer" in node_by_role:
                depends_map["developer"].add("planner")

        if mode in {"fix_bug", "debug"}:
            if "evaluator" in node_by_role and "researcher" in node_by_role:
                depends_map["researcher"].add("evaluator")

        return depends_map

    @staticmethod
    def _topological_sort(nodes: list[DagNode]) -> list[str]:
        node_ids = {node.id for node in nodes}
        indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}

        for node in nodes:
            for dep in node.depends_on:
                if dep not in node_ids:
                    continue
                indegree[node.id] += 1
                adjacency[dep].add(node.id)

        queue = sorted([node_id for node_id, degree in indegree.items() if degree == 0])
        order: list[str] = []

        while queue:
            current = queue.pop(0)
            order.append(current)
            for nxt in sorted(adjacency[current]):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        if len(order) != len(nodes):
            raise ValueError("Cycle detected while building DAG plan.")

        return order


def build_dynamic_planning_result(
    task: str,
    mode: str = "auto",
    registry: SkillRegistry | None = None,
    classifier: RuleBasedSkillClassifier | None = None,
    composer: TeamComposer | None = None,
    planner: DagPlanner | None = None,
) -> DynamicPlanningResult:
    """Create full dynamic planning output for orchestration execution loops."""

    registry = registry or build_default_registry()
    classifier = classifier or RuleBasedSkillClassifier()
    composer = composer or TeamComposer()
    planner = planner or DagPlanner()

    discovered = registry.discover()
    classified = classifier.classify(discovered)
    team_spec = composer.compose(TaskProfile(task=task, mode=mode), classified)
    dag_plan = planner.plan(team_spec)

    return DynamicPlanningResult(
        task=task,
        requested_mode=mode,
        discovered_skills=discovered,
        classified_skills=classified,
        team_spec=team_spec,
        dag_plan=dag_plan,
    )
