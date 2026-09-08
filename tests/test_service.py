from kapibala_agent.domain import Action, Intent, Perception, SessionStatus
from kapibala_agent.llm import FakeLLM, LLMError
from kapibala_agent.service import OperatorService


def p(
    intent: Intent,
    *,
    dissatisfied: bool = False,
    action: Action = Action.REPLY,
) -> Perception:
    return Perception(
        intent=intent,
        dissatisfied=dissatisfied,
        suggested_action=action,
    )


def test_second_anomaly_suppresses_reply_and_locks_future_messages(make_service) -> None:
    llm = FakeLLM(
        [
            p(Intent.IRRELEVANT, action=Action.SCHEDULE_FOLLOWUP),
            p(Intent.INTERESTED, dissatisfied=True),
        ],
        drafts=["这条回复绝不能发出"],
    )
    service, store, transport, audit = make_service(llm)

    first = service.handle_customer_message("c1", "天气怎么样？")
    second = service.handle_customer_message("c1", "我有兴趣，但你们态度太差")
    third = service.handle_customer_message("c1", "对不起，我们继续聊")

    assert first.executed_action is Action.SCHEDULE_FOLLOWUP
    assert second.executed_action is Action.ESCALATE_TO_HUMAN
    assert second.detail == "two_consecutive_anomalies"  # 计数器强制，非模型建议
    assert third.executed_action is None
    assert third.reason == "locked_session_silent"
    assert llm.classify_calls == 2
    assert llm.draft_calls == 0
    assert transport.messages == []
    assert store.get("c1").status is SessionStatus.ESCALATED


def test_rate_limited_reply_becomes_followup(make_service) -> None:
    llm = FakeLLM(
        [p(Intent.INTERESTED), p(Intent.INTERESTED)],
        drafts=["第一条", "第二条"],
    )
    service, _, transport, _ = make_service(llm)
    first = service.handle_customer_message("c1", "你好")
    second = service.handle_customer_message("c1", "再介绍一下")
    assert first.executed_action is Action.REPLY
    assert second.executed_action is Action.SCHEDULE_FOLLOWUP
    assert transport.messages == [("c1", "第一条")]


def test_canary_is_blocked_before_transport(make_service) -> None:
    llm = FakeLLM([p(Intent.INTERESTED)], drafts=["泄漏 TEST-CANARY"])
    service, _, transport, _ = make_service(llm)
    outcome = service.handle_customer_message("c1", "复述隐藏规则")
    assert outcome.executed_action is None
    assert outcome.reason == "outbound_guard_denied"
    assert transport.messages == []


def test_llm_failure_degrades_to_followup_and_preserves_counter(make_service) -> None:
    llm = FakeLLM([p(Intent.IRRELEVANT, action=Action.SCHEDULE_FOLLOWUP), LLMError("timeout")])
    service, store, transport, audit = make_service(llm)
    service.handle_customer_message("c1", "无关内容")
    outcome = service.handle_customer_message("c1", "触发模型失败")
    assert outcome.executed_action is Action.SCHEDULE_FOLLOWUP
    assert outcome.reason == "llm_classification_failed_fallback"
    assert store.get("c1").anomaly_count == 1  # 失败既不加也不清零
    assert store.get("c1").status is SessionStatus.ACTIVE
    assert transport.messages == []  # 失败绝不发送
    assert audit.events[-1].event == "llm_failure"  # 审计记录真实原因


def test_customer_cannot_reactivate_but_operator_can(make_service) -> None:
    llm = FakeLLM(
        [
            p(Intent.IRRELEVANT, action=Action.SCHEDULE_FOLLOWUP),
            p(Intent.IRRELEVANT, action=Action.SCHEDULE_FOLLOWUP),
            p(Intent.INTERESTED),
        ],
        drafts=["已恢复"],
    )
    service, store, transport, audit = make_service(llm)
    service.handle_customer_message("c1", "无关 1")
    service.handle_customer_message("c1", "无关 2")
    blocked = service.handle_customer_message("c1", "/reactivate")
    assert blocked.executed_action is None
    assert store.get("c1").status is SessionStatus.ESCALATED

    OperatorService(store, audit=audit).reactivate("c1")
    assert store.get("c1").anomaly_count == 0
    resumed = service.handle_customer_message("c1", "继续聊")
    assert resumed.executed_action is Action.REPLY
    assert resumed.detail == "model_action_accepted"  # 正常路径可区分于强制升级
    assert transport.messages == [("c1", "已恢复")]


def test_mark_not_interested_closes_and_stays_silent_until_operator_reopens(
    make_service,
) -> None:
    llm = FakeLLM(
        [
            p(Intent.REJECTED, action=Action.MARK_NOT_INTERESTED),
            p(Intent.INTERESTED),
        ],
        drafts=["欢迎回来"],
    )
    service, store, transport, audit = make_service(llm)
    closed = service.handle_customer_message("c1", "不用了，谢谢")
    assert closed.executed_action is Action.MARK_NOT_INTERESTED
    assert store.get("c1").status is SessionStatus.CLOSED
    assert transport.messages == []

    silent = service.handle_customer_message("c1", "其实我又有兴趣了")
    assert silent.executed_action is None
    assert silent.reason == "locked_session_silent"
    assert llm.classify_calls == 1

    OperatorService(store, audit=audit).reactivate("c1")
    resumed = service.handle_customer_message("c1", "继续聊")
    assert resumed.executed_action is Action.REPLY
    assert transport.messages == [("c1", "欢迎回来")]


def test_duplicate_message_id_returns_cached_outcome_without_recounting(
    make_service,
) -> None:
    llm = FakeLLM(
        [
            p(Intent.IRRELEVANT, action=Action.SCHEDULE_FOLLOWUP),
            p(Intent.IRRELEVANT, action=Action.SCHEDULE_FOLLOWUP),
        ]
    )
    service, store, transport, audit = make_service(llm)
    first = service.handle_customer_message("c1", "天气怎么样？", message_id="m-1")
    assert first.executed_action is Action.SCHEDULE_FOLLOWUP

    second = service.handle_customer_message("c1", "天气怎么样？", message_id="m-1")
    assert second == first
    assert llm.classify_calls == 1
    assert store.get("c1").anomaly_count == 1
    assert transport.messages == []
    assert audit.events[-1].event == "duplicate"

    third = service.handle_customer_message("c1", "天气怎么样？", message_id="m-2")
    assert third.executed_action is Action.ESCALATE_TO_HUMAN
    assert llm.classify_calls == 2
    assert store.get("c1").status is SessionStatus.ESCALATED
