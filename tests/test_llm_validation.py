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


def test_attempt_retries_only_retryable_errors() -> None:
    llm = GeminiLLM(api_key="unit-test-key")

    class StatusError(Exception):
        def __init__(self, status_code: int) -> None:
            super().__init__(f"provider {status_code}")
            self.status_code = status_code

    calls_400 = 0

    def fail_400() -> object:
        nonlocal calls_400
        calls_400 += 1
        raise StatusError(400)

    with pytest.raises(LLMError):
        llm._attempt(fail_400)
    assert calls_400 == 1

    flaky_calls = 0

    def flaky_429() -> object:
        nonlocal flaky_calls
        flaky_calls += 1
        if flaky_calls < 3:
            raise StatusError(429)
        return "ok"

    assert llm._attempt(flaky_429) == "ok"
    assert flaky_calls == 3

    plain_calls = 0

    def fail_plain() -> object:
        nonlocal plain_calls
        plain_calls += 1
        raise RuntimeError("network down")

    with pytest.raises(LLMError):
        llm._attempt(fail_plain)
    assert plain_calls == 3
