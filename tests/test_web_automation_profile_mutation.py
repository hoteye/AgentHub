import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.web_automation.service import BrowserService
from shared.web_automation.storage import load_state

class BrowserProfileMutationTest(unittest.TestCase):
    def test_create_and_delete_profile_persists_runtime_overrides(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            try:
                service = BrowserService()
                created = service.create_profile(name="review", driver="openclaw")

                self.assertEqual(created.name, "review")
                self.assertIn("review", service.state.profiles)
                self.assertIn("review", load_state().get("profile_overrides", {}))

                deleted = service.delete_profile("review")

                self.assertTrue(deleted)
                self.assertNotIn("review", service.state.profiles)
                self.assertNotIn("review", load_state().get("profile_overrides", {}))
            finally:
                os.chdir(original_cwd)

    def test_reset_profile_rejects_existing_session(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            try:
                service = BrowserService()
                service.create_profile(
                    name="usercopy",
                    driver="existing-session",
                    user_data_dir=temp_dir,
                )

                with self.assertRaisesRegex(ValueError, "not resettable"):
                    service.reset_profile("usercopy")
            finally:
                os.chdir(original_cwd)
