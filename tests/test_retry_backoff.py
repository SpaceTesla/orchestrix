import unittest
from unittest.mock import MagicMock

from orchestrix.retry.backoff import (
    compute_retry_delay_seconds,
    should_retry,
)


def _rng_without_jitter() -> MagicMock:
    rng = MagicMock()
    rng.uniform.return_value = 0.0
    return rng


class RetryBackoffTests(unittest.TestCase):
    def test_should_retry_respects_max_attempts(self) -> None:
        self.assertTrue(should_retry(1, 3))
        self.assertTrue(should_retry(2, 3))
        self.assertFalse(should_retry(3, 3))

    def test_exponential_backoff_without_jitter(self) -> None:
        rng = _rng_without_jitter()
        delay = compute_retry_delay_seconds(
            1,
            base_delay=1.0,
            max_delay=300.0,
            rng=rng,
        )
        self.assertEqual(delay, 2.0)

        delay = compute_retry_delay_seconds(
            2,
            base_delay=1.0,
            max_delay=300.0,
            rng=rng,
        )
        self.assertEqual(delay, 4.0)

    def test_backoff_capped_at_max_delay(self) -> None:
        rng = _rng_without_jitter()
        delay = compute_retry_delay_seconds(
            20,
            base_delay=1.0,
            max_delay=10.0,
            rng=rng,
        )
        self.assertEqual(delay, 10.0)

    def test_attempt_count_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            compute_retry_delay_seconds(0, base_delay=1.0, max_delay=10.0)


if __name__ == "__main__":
    unittest.main()
