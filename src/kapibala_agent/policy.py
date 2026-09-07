from __future__ import annotations

from .domain import Action, Intent, Perception

_FALLBACK_BY_INTENT: dict[Intent, Action] = {
    Intent.INTERESTED: Action.REPLY,
    Intent.NEEDS_MORE_INFO: Action.REPLY,
    Intent.REJECTED: Action.MARK_NOT_INTERESTED,
    Intent.IRRELEVANT: Action.SCHEDULE_FOLLOWUP,
    Intent.OTHER: Action.SCHEDULE_FOLLOWUP,
}

_COMPATIBLE_ACTIONS: dict[Intent, frozenset[Action]] = {
    Intent.INTERESTED: frozenset(
        {Action.REPLY, Action.SCHEDULE_FOLLOWUP, Action.ESCALATE_TO_HUMAN}
    ),
    Intent.NEEDS_MORE_INFO: frozenset(
        {Action.REPLY, Action.SCHEDULE_FOLLOWUP, Action.ESCALATE_TO_HUMAN}
    ),
    Intent.REJECTED: frozenset({Action.MARK_NOT_INTERESTED, Action.ESCALATE_TO_HUMAN}),
    Intent.IRRELEVANT: frozenset(
        {Action.REPLY, Action.SCHEDULE_FOLLOWUP, Action.ESCALATE_TO_HUMAN}
    ),
    Intent.OTHER: frozenset({Action.REPLY, Action.SCHEDULE_FOLLOWUP, Action.ESCALATE_TO_HUMAN}),
}


def clamp_action(perception: Perception) -> tuple[Action, str]:
    """Accept only intent-compatible suggestions; otherwise tighten to a safe fallback."""
    if perception.suggested_action in _COMPATIBLE_ACTIONS[perception.intent]:
        return perception.suggested_action, "suggestion_compatible"
    return _FALLBACK_BY_INTENT[perception.intent], "suggestion_clamped"
