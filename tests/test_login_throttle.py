from __future__ import annotations

from auth.login_throttle import LoginThrottle


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_identifier_is_locked_after_threshold_and_expires_after_window():
    clock = Clock()
    throttle = LoginThrottle(
        window_seconds=60,
        identifier_limit=3,
        address_limit=10,
        clock=clock,
    )

    assert throttle.retry_after("Student", "127.0.0.1") == 0
    assert throttle.record_failure("Student", "127.0.0.1") == 0
    assert throttle.record_failure("student", "127.0.0.1") == 0
    assert throttle.record_failure("STUDENT", "127.0.0.1") == 60
    assert throttle.retry_after("student", "127.0.0.1") == 60

    clock.now += 61
    assert throttle.retry_after("student", "127.0.0.1") == 0


def test_address_limit_applies_across_different_identifiers():
    clock = Clock()
    throttle = LoginThrottle(
        window_seconds=60,
        identifier_limit=5,
        address_limit=2,
        clock=clock,
    )
    assert throttle.record_failure("user-a", "127.0.0.1") == 0
    assert throttle.record_failure("user-b", "127.0.0.1") == 60
    assert throttle.retry_after("user-c", "127.0.0.1") == 60
    assert throttle.retry_after("user-c", "127.0.0.2") == 0
