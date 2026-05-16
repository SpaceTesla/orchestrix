import unittest
from unittest.mock import patch

from pydantic import ValidationError

from orchestrix.config import Settings


class SettingsValidationTests(unittest.TestCase):
    def test_reaper_threshold_must_exceed_job_timeout(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                postgres_user="u",
                postgres_password="p",
                postgres_db="d",
                database_url="postgresql://u:p@localhost/d",
                redis_host="localhost",
                redis_port=6379,
                redis_url="redis://localhost:6379/0",
                job_timeout_seconds=60.0,
                reaper_threshold_seconds=60.0,
            )

    def test_valid_timeout_pair(self) -> None:
        settings = Settings(
            postgres_user="u",
            postgres_password="p",
            postgres_db="d",
            database_url="postgresql://u:p@localhost/d",
            redis_host="localhost",
            redis_port=6379,
            redis_url="redis://localhost:6379/0",
            job_timeout_seconds=60.0,
            reaper_threshold_seconds=180.0,
        )
        self.assertEqual(settings.job_timeout_seconds, 60.0)
        self.assertEqual(settings.reaper_threshold_seconds, 180.0)


if __name__ == "__main__":
    unittest.main()
