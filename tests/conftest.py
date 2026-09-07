from __future__ import annotations

from dataclasses import dataclass

import pytest

from kapibala_agent.audit import MemoryAuditSink
from kapibala_agent.executor import Executor, RecordingTransport
from kapibala_agent.llm import FakeLLM
from kapibala_agent.service import AgentService
from kapibala_agent.store import SessionStore


@dataclass
class FakeClock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value


@pytest.fixture
def make_service(tmp_path):
    def factory(llm: FakeLLM, *, clock: FakeClock | None = None):
        store = SessionStore(tmp_path / "agent.db")
        transport = RecordingTransport()
        audit = MemoryAuditSink()
        executor = Executor(
            store,
            transport,
            clock=clock or FakeClock(),
            canary=llm.canary,
        )
        service = AgentService(store, llm, executor, audit)
        return service, store, transport, audit

    return factory
