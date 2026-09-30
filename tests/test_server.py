from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from uned_study.server import dashboard


class _Storage:
    def preferences(self, user_id: str) -> dict[str, object]:
        return {}


class _Content:
    def __init__(self) -> None:
        self.subjects: dict[str, object] = {}
        self.last_sync: str | None = None
        self.last_error: str | None = None
        self.sync_calls = 0

    async def sync(self) -> bool:
        self.sync_calls += 1
        self.last_sync = "checked"
        return True


class DashboardSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_syncs_content_before_rendering(self) -> None:
        content = _Content()
        request = SimpleNamespace(
            headers={"X-Debug-User-Id": "test-user"},
            app={
                "config": SimpleNamespace(dev_mode=True),
                "storage": _Storage(),
                "content": content,
            },
        )

        response = await dashboard(request)

        self.assertEqual(content.sync_calls, 1)
        payload = json.loads(response.text)
        self.assertEqual(payload["subjects"], [])
        self.assertEqual(payload["content"]["last_sync"], "checked")


if __name__ == "__main__":
    unittest.main()
