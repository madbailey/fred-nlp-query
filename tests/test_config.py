from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fred_query.config import get_settings


class ConfigTest(unittest.TestCase):
    def test_openai_key_alias_from_env_file(self) -> None:
        get_settings.cache_clear()
        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("FRED_API_KEY=test-fred\nOPENAI_KEY=test-openai\n", encoding="utf-8")

            settings = get_settings(env_path)

        self.assertEqual(settings.fred_api_key, "test-fred")
        self.assertEqual(settings.openai_api_key, "test-openai")


if __name__ == "__main__":
    unittest.main()
