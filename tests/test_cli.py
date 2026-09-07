from kapibala_agent import cli
from kapibala_agent.domain import SessionStatus
from kapibala_agent.store import SessionStore


def test_admin_reactivate_never_constructs_llm(tmp_path, monkeypatch) -> None:
    database = tmp_path / "agent.db"
    monkeypatch.setenv("AGENT_DB_PATH", str(database))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))

    def forbidden_llm():
        raise AssertionError("operator path must not construct Gemini")

    monkeypatch.setattr(cli, "GeminiLLM", forbidden_llm)
    assert cli.main(["admin", "reactivate", "c1"]) == 0
    assert SessionStore(database).get("c1").status is SessionStatus.ACTIVE
