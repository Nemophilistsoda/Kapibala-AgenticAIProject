from concurrent.futures import ThreadPoolExecutor

from kapibala_agent.domain import Session, SessionStatus
from kapibala_agent.store import SessionStore


def test_rolling_window_boundary_and_denials_do_not_extend_it(tmp_path) -> None:
    store = SessionStore(tmp_path / "agent.db")
    store.save(Session("c1"))
    assert store.reserve_send("c1", now=0.0, window_seconds=60.0) is True
    for instant in (10.0, 20.0, 30.0, 59.999):
        assert store.reserve_send("c1", now=instant, window_seconds=60.0) is False
    assert store.reserve_send("c1", now=60.0, window_seconds=60.0) is True


def test_locked_session_cannot_reserve_send(tmp_path) -> None:
    store = SessionStore(tmp_path / "agent.db")
    store.save(Session("c1", status=SessionStatus.ESCALATED, anomaly_count=2))
    assert store.reserve_send("c1", now=100.0, window_seconds=60.0) is False


def test_state_survives_new_store_instance(tmp_path) -> None:
    path = tmp_path / "agent.db"
    first = SessionStore(path)
    first.save(Session("c1", status=SessionStatus.ESCALATED, anomaly_count=2))
    restored = SessionStore(path).get("c1")
    assert restored.status is SessionStatus.ESCALATED
    assert restored.anomaly_count == 2


def test_concurrent_reservations_allow_exactly_one_send(tmp_path) -> None:
    store = SessionStore(tmp_path / "agent.db")
    store.save(Session("c1"))
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(
            pool.map(
                lambda _: store.reserve_send("c1", now=100.0, window_seconds=60.0),
                range(10),
            )
        )
    assert results.count(True) == 1
    assert results.count(False) == 9
