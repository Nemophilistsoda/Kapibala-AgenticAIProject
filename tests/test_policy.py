from kapibala_agent.domain import Action, Intent, Perception
from kapibala_agent.policy import clamp_action


def test_incompatible_model_action_is_clamped() -> None:
    perception = Perception(
        intent=Intent.INTERESTED,
        dissatisfied=False,
        suggested_action=Action.MARK_NOT_INTERESTED,
    )
    action, reason = clamp_action(perception)
    assert action is Action.REPLY
    assert reason == "suggestion_clamped"
