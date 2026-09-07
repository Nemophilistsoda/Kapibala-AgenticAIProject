from __future__ import annotations

from collections.abc import Callable
from time import time
from typing import Protocol

from .domain import Action, Outcome, SessionStatus
from .store import SessionStore


class Transport(Protocol):
    def send(self, customer_id: str, text: str) -> None: ...


class ConsoleTransport:
    def send(self, customer_id: str, text: str) -> None:
        print(f"Agent[{customer_id}]: {text}")


class RecordingTransport:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, customer_id: str, text: str) -> None:
        self.messages.append((customer_id, text))


class Executor:
    """The sole side-effect boundary for all four actions."""

    def __init__(
        self,
        store: SessionStore,
        transport: Transport,
        *,
        clock: Callable[[], float] = time,
        window_seconds: float = 60.0,
        canary: str,
    ) -> None:
        self._store = store
        self._transport = transport
        self._clock = clock
        self._window_seconds = window_seconds
        self._canary = canary
        self._dispatch = {
            Action.REPLY: self._reply,
            Action.SCHEDULE_FOLLOWUP: self._schedule_followup,
            Action.ESCALATE_TO_HUMAN: self._escalate,
            Action.MARK_NOT_INTERESTED: self._mark_not_interested,
        }

    def execute(
        self,
        customer_id: str,
        action: Action,
        *,
        draft_reply: str | None = None,
    ) -> Outcome:
        current = self._store.get(customer_id)
        expected_status = {
            Action.REPLY: SessionStatus.ACTIVE,
            Action.SCHEDULE_FOLLOWUP: SessionStatus.ACTIVE,
            Action.ESCALATE_TO_HUMAN: SessionStatus.ESCALATED,
            Action.MARK_NOT_INTERESTED: SessionStatus.CLOSED,
        }[action]
        if current.status is not expected_status:
            return Outcome(
                customer_id=customer_id,
                status=current.status,
                executed_action=None,
                reason="executor_state_gate_denied",
            )
        return self._dispatch[action](customer_id, draft_reply)

    def _reply(self, customer_id: str, draft_reply: str | None) -> Outcome:
        current = self._store.get(customer_id)
        if current.status is not SessionStatus.ACTIVE:
            return Outcome(customer_id, current.status, None, "reply_locked")
        if not draft_reply or self._canary in draft_reply:
            return Outcome(customer_id, current.status, None, "outbound_guard_denied")

        reserved = self._store.reserve_send(
            customer_id,
            now=self._clock(),
            window_seconds=self._window_seconds,
        )
        if not reserved:
            return Outcome(
                customer_id,
                current.status,
                Action.SCHEDULE_FOLLOWUP,
                "reply_rate_limited_followup_scheduled",
            )

        self._transport.send(customer_id, draft_reply)
        return Outcome(
            customer_id,
            current.status,
            Action.REPLY,
            "reply_sent",
            customer_visible_text=draft_reply,
        )

    def _schedule_followup(self, customer_id: str, _: str | None) -> Outcome:
        current = self._store.get(customer_id)
        return Outcome(
            customer_id,
            current.status,
            Action.SCHEDULE_FOLLOWUP,
            "followup_scheduled",
        )

    def _escalate(self, customer_id: str, _: str | None) -> Outcome:
        current = self._store.get(customer_id)
        return Outcome(
            customer_id,
            current.status,
            Action.ESCALATE_TO_HUMAN,
            "escalated",
        )

    def _mark_not_interested(self, customer_id: str, _: str | None) -> Outcome:
        current = self._store.get(customer_id)
        return Outcome(
            customer_id,
            current.status,
            Action.MARK_NOT_INTERESTED,
            "conversation_closed",
        )
