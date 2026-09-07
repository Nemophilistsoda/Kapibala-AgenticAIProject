from __future__ import annotations

from .domain import Action, Intent, Perception, Session, SessionStatus, Transition


def transition(
    current: Session,
    perception: Perception,
    requested_action: Action,
    *,
    escalation_threshold: int = 2,
) -> Transition:
    """Apply deterministic state rules to one valid model observation.

    A message that is both irrelevant and dissatisfied still counts once: the
    requirement says two consecutive *messages*, not two independent signals.
    """
    if current.status is not SessionStatus.ACTIVE:
        raise ValueError("locked sessions cannot consume customer observations")

    is_anomaly = perception.intent is Intent.IRRELEVANT or perception.dissatisfied
    anomaly_count = current.anomaly_count + 1 if is_anomaly else 0

    if anomaly_count >= escalation_threshold:
        return Transition(
            session=current.updated(
                status=SessionStatus.ESCALATED,
                anomaly_count=anomaly_count,
            ),
            action=Action.ESCALATE_TO_HUMAN,
            forced=True,
            reason="two_consecutive_anomalies",
        )

    if requested_action is Action.ESCALATE_TO_HUMAN:
        status = SessionStatus.ESCALATED
    elif requested_action is Action.MARK_NOT_INTERESTED:
        status = SessionStatus.CLOSED
    else:
        status = SessionStatus.ACTIVE

    return Transition(
        session=current.updated(status=status, anomaly_count=anomaly_count),
        action=requested_action,
        forced=False,
        reason="model_action_accepted",
    )
