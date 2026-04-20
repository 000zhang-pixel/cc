from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db.models import Base, SyncCursor, make_engine
from db.sync.syncer import FeishuSyncer


class FakeFeishu:
    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []

    def list_records(self, table_id: str, filter_str: str | None = None, page_size: int = 100):
        self.calls.append((table_id, filter_str))
        return []


TABLE_IDS = {
    "sku": "tbl_sku",
    "plan": "tbl_plan",
    "content": "tbl_content",
    "publish": "tbl_publish",
    "material": "tbl_material",
    "tag": "tbl_tag",
}

CURSOR_KEYS = [
    "feishu_sku",
    "feishu_plan",
    "feishu_content",
    "feishu_publish",
    "feishu_material",
    "feishu_tag",
]


class SyncStrategyTests(unittest.TestCase):
    def setUp(self):
        self._old_env = dict(os.environ)
        self.tempdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tempdir.name, "sync.db")
        self.engine = make_engine(db_path)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            now = datetime.utcnow() - timedelta(minutes=5)
            for key in CURSOR_KEYS:
                session.add(SyncCursor(table_name=key, last_sync_at=now, sync_count=1))
            session.commit()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_env)
        self.tempdir.cleanup()

    def _make_syncer(self, *, mode: str = "hybrid", full_every: int = 3):
        os.environ["FEISHU_SYNC_MODE"] = mode
        os.environ["FEISHU_SYNC_FULL_SCAN_EVERY"] = str(full_every)
        fake = FakeFeishu()
        return FeishuSyncer(fake, TABLE_IDS, engine=self.engine), fake

    def test_periodic_hybrid_sync_uses_formula_filters_between_full_rescans(self):
        syncer, fake = self._make_syncer(mode="hybrid", full_every=3)

        with self.assertLogs("db.sync.syncer", level="INFO") as logs:
            syncer.sync_all(reason="periodic")

        self.assertEqual(len(fake.calls), 6)
        self.assertTrue(all(filter_str is not None for _, filter_str in fake.calls))
        self.assertTrue(any("Starting periodic hybrid sync of all tables" in line for line in logs.output))

    def test_periodic_hybrid_sync_forces_full_scan_on_configured_cadence(self):
        syncer, fake = self._make_syncer(mode="hybrid", full_every=2)

        syncer.sync_all(reason="periodic")
        fake.calls.clear()

        syncer.sync_all(reason="periodic")

        self.assertEqual(len(fake.calls), 6)
        self.assertTrue(all(filter_str is None for _, filter_str in fake.calls))

    def test_startup_sync_is_always_full_scan_even_in_hybrid_mode(self):
        syncer, fake = self._make_syncer(mode="hybrid", full_every=2)

        syncer.sync_all(reason="startup")

        self.assertEqual(len(fake.calls), 6)
        self.assertTrue(all(filter_str is None for _, filter_str in fake.calls))


if __name__ == "__main__":
    unittest.main()
