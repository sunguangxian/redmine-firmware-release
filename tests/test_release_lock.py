import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from release_tool.release_lock import PublishLockTimeout, acquire_publish_lock


class ReleaseLockTest(unittest.TestCase):
    def test_second_owner_cannot_acquire_active_lock(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "release_tool.config_store.PROJECT_ROOT", Path(temp_dir)
        ):
            with acquire_publish_lock("demo:V1", owner="owner-a", wait_seconds=0, ttl_seconds=60):
                with self.assertRaises(PublishLockTimeout):
                    with acquire_publish_lock("demo:V1", owner="owner-b", wait_seconds=0, ttl_seconds=60):
                        pass

    def test_lock_is_released_after_context(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "release_tool.config_store.PROJECT_ROOT", Path(temp_dir)
        ):
            with acquire_publish_lock("demo:V1", owner="owner-a", wait_seconds=0, ttl_seconds=60):
                pass

            with acquire_publish_lock("demo:V1", owner="owner-b", wait_seconds=0, ttl_seconds=60) as owner:
                self.assertEqual(owner, "owner-b")

    def test_expired_lock_can_be_replaced(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "release_tool.config_store.PROJECT_ROOT", Path(temp_dir)
        ):
            with acquire_publish_lock("demo:V1", owner="owner-a", wait_seconds=0, ttl_seconds=1):
                pass

            with acquire_publish_lock("demo:V1", owner="owner-b", wait_seconds=0, ttl_seconds=1) as owner:
                self.assertEqual(owner, "owner-b")


if __name__ == "__main__":
    unittest.main()
