from __future__ import annotations

from auth.store import AuthStore


class FakeCursor:
    def __init__(self, pool):
        self.pool = pool

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def execute(self, statement, parameters):
        self.pool.calls += 1
        self.pool.last_statement = statement
        self.pool.last_parameters = parameters
        if self.pool.failures_remaining:
            self.pool.failures_remaining -= 1
            raise RuntimeError("temporary database error")


class FakeConnection:
    def __init__(self, pool):
        self.pool = pool

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def cursor(self):
        return FakeCursor(self.pool)


class FakePool:
    def __init__(self, failures_remaining=0):
        self.failures_remaining = failures_remaining
        self.calls = 0
        self.last_statement = ""
        self.last_parameters = None

    def connection(self):
        return FakeConnection(self)


def test_admin_audit_insert_retries_once_after_transient_failure():
    pool = FakePool(failures_remaining=1)
    AuthStore(pool).log_admin_action(
        7, "student_profile_updated", "user", 42, {"username": "student"}
    )
    assert pool.calls == 2
    assert "INSERT INTO admin_audit_log" in pool.last_statement
    assert pool.last_parameters[0:4] == (7, "student_profile_updated", "user", "42")


def test_admin_audit_insert_raises_after_second_failure():
    pool = FakePool(failures_remaining=2)
    try:
        AuthStore(pool).log_admin_action(7, "test", "user", 42, {})
    except RuntimeError as exc:
        assert "temporary database error" in str(exc)
    else:
        raise AssertionError("Persistent audit failures must be raised to the caller.")
    assert pool.calls == 2
