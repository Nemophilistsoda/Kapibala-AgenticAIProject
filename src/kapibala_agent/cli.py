from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .audit import JsonlAuditSink
from .executor import ConsoleTransport, Executor
from .llm import GeminiLLM, LLMError
from .service import AgentService, OperatorService
from .store import SessionStore


def _runtime_paths() -> tuple[SessionStore, JsonlAuditSink]:
    load_dotenv()
    store = SessionStore(os.getenv("AGENT_DB_PATH", "agent.db"))
    audit = JsonlAuditSink(Path(os.getenv("AUDIT_LOG_PATH", "audit.jsonl")))
    return store, audit


def _build_customer_service() -> AgentService:
    store, audit = _runtime_paths()
    llm = GeminiLLM()
    executor = Executor(
        store,
        ConsoleTransport(),
        window_seconds=float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
        canary=llm.canary,
    )
    return AgentService(store, llm, executor, audit)


def _build_operator_service() -> OperatorService:
    store, audit = _runtime_paths()
    return OperatorService(store, audit)


def _chat(service: AgentService, customer_id: str) -> int:
    print("输入客户消息；输入 /quit 退出。人工恢复必须使用独立的 admin 子命令。")
    while True:
        try:
            message = input(f"Customer[{customer_id}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if message == "/quit":
            return 0
        if not message:
            continue
        outcome = service.handle_customer_message(customer_id, message)
        if outcome.executed_action is None:
            print(f"[system] silent: {outcome.reason} (state={outcome.status.value})")
        elif outcome.executed_action.value != "reply":
            print(
                f"[system] action={outcome.executed_action.value} "
                f"state={outcome.status.value} reason={outcome.reason}"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KapibalaAI 获客初筛 Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    chat = subparsers.add_parser("chat", help="客户消息入口")
    chat.add_argument("--customer-id", default="demo-customer")
    admin = subparsers.add_parser("admin", help="人工操作入口")
    admin_subparsers = admin.add_subparsers(dest="admin_command", required=True)
    reactivate = admin_subparsers.add_parser("reactivate", help="重新激活会话")
    reactivate.add_argument("customer_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "chat":
        try:
            service = _build_customer_service()
        except LLMError as exc:
            print(f"配置错误：{exc}")
            return 2
        return _chat(service, args.customer_id)
    if args.command == "admin" and args.admin_command == "reactivate":
        outcome = _build_operator_service().reactivate(args.customer_id)
        print(f"已重新激活 {args.customer_id}，state={outcome.status.value}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
