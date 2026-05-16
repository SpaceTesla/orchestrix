from unittest.mock import MagicMock

import pytest

from orchestrix.retry.backoff import (
    compute_retry_delay_seconds,
    should_retry,
)


def _rng_without_jitter() -> MagicMock:
    rng = MagicMock()
    rng.uniform.return_value = 0.0
    return rng


def test_should_retry_respects_max_attempts() -> None:
    assert should_retry(1, 3) is True
    assert should_retry(2, 3) is True
    assert should_retry(3, 3) is False


def test_exponential_backoff_without_jitter() -> None:
    rng = _rng_without_jitter()

    assert (
        compute_retry_delay_seconds(
            1,
            base_delay=1.0,
            max_delay=300.0,
            rng=rng,
        )
        == 2.0
    )

    assert (
        compute_retry_delay_seconds(
            2,
            base_delay=1.0,
            max_delay=300.0,
            rng=rng,
        )
        == 4.0
    )


def test_backoff_capped_at_max_delay() -> None:
    rng = _rng_without_jitter()
    delay = compute_retry_delay_seconds(
        20,
        base_delay=1.0,
        max_delay=10.0,
        rng=rng,
    )
    assert delay == 10.0


def test_attempt_count_must_be_positive() -> None:
    with pytest.raises(ValueError):
        compute_retry_delay_seconds(0, base_delay=1.0, max_delay=10.0)
