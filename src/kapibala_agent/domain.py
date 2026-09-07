from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Intent(StrEnum):
    INTERESTED = "interested"
    NEEDS_MORE_INFO = "needs_more_info"
    REJECTED = "rejected"
    IRRELEVANT = "irrelevant"
    OTHER = "other"


class Action(StrEnum):
    REPLY = "reply"
    SCHEDULE_FOLLOWUP = "schedule_followup"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    MARK_NOT_INTERESTED = "mark_not_interested"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    ESCALATED = "escalated"
    CLOSED = "closed"


class Perception(BaseModel):
    """Untrusted model output. Every field is required and extra fields fail."""

    model_config = ConfigDict(extra="forbid", strict=True)

    intent: Intent
    dissatisfied: bool
    suggested_action: Action


@dataclass(frozen=True, slots=True)
class Session:
    customer_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    anomaly_count: int = 0
    last_sent_at: float | None = None

    def updated(self, **changes: object) -> Session:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class Transition:
    session: Session
    action: Action
    forced: bool
    reason: str


@dataclass(frozen=True, slots=True)
class Outcome:
    customer_id: str
    status: SessionStatus
    executed_action: Action | None
    reason: str
    customer_visible_text: str | None = None
