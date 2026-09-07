import pytest

from kapibala_agent.domain import Action, Intent
from kapibala_agent.llm import GeminiLLM, LLMError


def test_wire_json_is_validated_again_locally() -> None:
    parsed = GeminiLLM._parse_perception(
        '{"intent":"interested","dissatisfied":false,"suggested_action":"reply"}'
    )
    assert parsed.intent is Intent.INTERESTED
    assert parsed.suggested_action is Action.REPLY


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"intent":"interested","dissatisfied":"false","suggested_action":"reply"}',
        '{"intent":"interested","dissatisfied":false,"suggested_action":"delete"}',
        '{"intent":"interested","dissatisfied":false,"suggested_action":"reply","extra":1}',
    ],
)
def test_malformed_or_relaxed_wire_json_fails_closed(payload: str) -> None:
    with pytest.raises(LLMError):
        GeminiLLM._parse_perception(payload)
