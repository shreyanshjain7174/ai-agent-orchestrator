from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeMemoryStore:
    """Simple in-memory state recorder for loop tests."""

    entries: list[dict] = field(default_factory=list)

    def add(self, item: dict) -> None:
        self.entries.append(item)

    def latest(self, limit: int = 5) -> list[dict]:
        return self.entries[-limit:]
