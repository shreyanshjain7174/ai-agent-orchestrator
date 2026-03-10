from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeDagExecutor:
    """Captures planned execution order without executing external systems."""

    runs: list[list[str]] = field(default_factory=list)

    def execute(self, order: list[str]) -> dict:
        self.runs.append(order)
        return {
            "executed": True,
            "order": order,
            "node_count": len(order),
        }
