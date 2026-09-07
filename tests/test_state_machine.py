import pytest

from kapibala_agent.domain import Action, Intent, Perception, Session, SessionStatus
from kapibala_agent.state_machine import transition


def perception(intent: Intent, dissatisfied: bool = False) -> Perception:
    return Perception(
        intent=intent,
        dissatisfied=dissatisfied,
        suggested_action=Action.REPLY,
    )


def test_both_anomaly_signals_increment_only_once() -> None:
    planned = transition(
        Session("c1"),
        perception(Intent.IRRELEVANT, dissatisfied=True),
        Action.REPLY,
    )
    assert planned.session.anomaly_count == 1
    assert planned.session.status is SessionStatus.ACTIVE


def test_normal_message_resets_shared_counter() -> None:
    current = Session("c1", anomaly_count=1)
    planned = transition(current, perception(Intent.INTERESTED), Action.REPLY)
    assert planned.session.anomaly_count == 0


def test_second_consecutive_anomaly_forces_escalation() -> None:
    current = Session("c1", anomaly_count=1)
    planned = transition(
        current,
        perception(Intent.INTERESTED, dissatisfied=True),
        Action.REPLY,
    )
    assert planned.forced is True
    assert planned.action is Action.ESCALATE_TO_HUMAN
    assert planned.session.status is SessionStatus.ESCALATED


def test_locked_state_rejects_customer_observation() -> None:
    with pytest.raises(ValueError):
        transition(
            Session("c1", status=SessionStatus.ESCALATED),
            perception(Intent.INTERESTED),
            Action.REPLY,
        )
