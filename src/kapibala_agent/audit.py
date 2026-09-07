from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from time import time
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuditEvent:
    customer_id: str
    event: str
    reason: str
    intent: str | None = None
    dissatisfied: bool | None = None
    proposed_action: str | None = None
    executed_action: str | None = None
    status: str | None = None
    timestamp: float = 0.0


class AuditSink(Protocol):
    def write(self, event: AuditEvent) -> None: ...


class JsonlAuditSink:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def write(self, event: AuditEvent) -> None:
        payload = asdict(event)
        if not payload["timestamp"]:
            payload["timestamp"] = time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class MemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def write(self, event: AuditEvent) -> None:
        self.events.append(event)
