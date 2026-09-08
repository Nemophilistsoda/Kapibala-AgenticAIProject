from __future__ import annotations

from threading import RLock

from .audit import AuditEvent, AuditSink
from .domain import Action, Outcome, SessionStatus
from .executor import Executor
from .llm import LLMClient
from .policy import clamp_action
from .state_machine import transition
from .store import SessionStore


class AgentService:
    def __init__(
        self,
        store: SessionStore,
        llm: LLMClient,
        executor: Executor,
        audit: AuditSink,
        *,
        escalation_threshold: int = 2,
    ) -> None:
        self._store = store
        self._llm = llm
        self._executor = executor
        self._audit = audit
        self._escalation_threshold = escalation_threshold
        # 固定 64 把锁分片：内存有上限，不随 customer_id 增长；
        # 同一客户永远落在同一片，单客户互斥语义不变，不同客户偶尔同片只是多等一下。
        self._lock_stripes: list[RLock] = [RLock() for _ in range(64)]
        # 已处理消息的幂等表（进程内）：(customer_id, message_id) -> 上次 Outcome。
        # 有界 FIFO，满 1024 条丢最旧；注意失败结果也会被记住，
        # 客户端遇到失败想重试请换一个新的 message_id。
        self._seen_guard = RLock()
        self._seen: dict[tuple[str, str], Outcome] = {}
        self._seen_limit = 1024

    def _lock_for(self, customer_id: str) -> RLock:
        return self._lock_stripes[hash(customer_id) % len(self._lock_stripes)]

    def handle_customer_message(
        self, customer_id: str, message: str, *, message_id: str | None = None
    ) -> Outcome:
        if not customer_id.strip() or not message.strip():
            raise ValueError("customer_id and message must be non-empty")
        if message_id is not None:
            if not message_id.strip():
                raise ValueError("message_id must be non-empty when provided")
            with self._seen_guard:
                cached = self._seen.get((customer_id, message_id))
            if cached is not None:
                self._audit.write(
                    AuditEvent(
                        customer_id,
                        "duplicate",
                        "duplicate_message_id_suppressed",
                        status=cached.status.value,
                    )
                )
                return cached
        outcome = self._handle_uncached(customer_id, message)
        if message_id is not None:
            with self._seen_guard:
                if len(self._seen) >= self._seen_limit:
                    self._seen.pop(next(iter(self._seen)))
                self._seen[(customer_id, message_id)] = outcome
        return outcome

    def _handle_uncached(self, customer_id: str, message: str) -> Outcome:
        with self._lock_for(customer_id):
            current = self._store.get(customer_id)
            if current.status is not SessionStatus.ACTIVE:
                outcome = Outcome(
                    customer_id,
                    current.status,
                    None,
                    "locked_session_silent",
                )
                self._audit.write(
                    AuditEvent(customer_id, "pre_gate", outcome.reason, status=current.status.value)
                )
                return outcome

            try:
                perception = self._llm.classify(message)
            except Exception as exc:
                outcome = Outcome(customer_id, current.status, None, "llm_classification_failed")
                self._audit.write(
                    AuditEvent(
                        customer_id,
                        "llm_failure",
                        f"{outcome.reason}:{type(exc).__name__}",
                        status=current.status.value,
                    )
                )
                return outcome

            requested_action, policy_reason = clamp_action(perception)
            planned = transition(
                current,
                perception,
                requested_action,
                escalation_threshold=self._escalation_threshold,
            )
            self._store.save(planned.session)

            draft_reply: str | None = None
            if planned.action is Action.REPLY:
                try:
                    draft_reply = self._llm.draft_reply(message, perception)
                except Exception as exc:
                    outcome = Outcome(
                        customer_id,
                        planned.session.status,
                        None,
                        "llm_reply_failed",
                    )
                    self._audit.write(
                        AuditEvent(
                            customer_id,
                            "llm_failure",
                            f"{outcome.reason}:{type(exc).__name__}",
                            intent=perception.intent.value,
                            dissatisfied=perception.dissatisfied,
                            proposed_action=perception.suggested_action.value,
                            status=planned.session.status.value,
                        )
                    )
                    return outcome

            outcome = self._executor.execute(
                customer_id,
                planned.action,
                draft_reply=draft_reply,
            )
            self._audit.write(
                AuditEvent(
                    customer_id,
                    "decision",
                    f"{policy_reason};{planned.reason};{outcome.reason}",
                    intent=perception.intent.value,
                    dissatisfied=perception.dissatisfied,
                    proposed_action=perception.suggested_action.value,
                    executed_action=(
                        outcome.executed_action.value if outcome.executed_action else None
                    ),
                    status=outcome.status.value,
                    forced=planned.forced,
                )
            )
            return outcome


class OperatorService:
    """Trusted operator entry point; deliberately has no LLM dependency."""

    def __init__(self, store: SessionStore, audit: AuditSink) -> None:
        self._store = store
        self._audit = audit

    def reactivate(self, customer_id: str) -> Outcome:
        if not customer_id.strip():
            raise ValueError("customer_id must be non-empty")
        session = self._store.reactivate(customer_id)
        outcome = Outcome(customer_id, session.status, None, "operator_reactivated")
        self._audit.write(
            AuditEvent(customer_id, "operator", outcome.reason, status=session.status.value)
        )
        return outcome
