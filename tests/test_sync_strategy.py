from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db.models import Base, Content, Plan, Prompt, SyncCursor, make_engine
from db.repo import init_engine, update_content_status
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
    "prompt": "tbl_prompt",
    "content": "tbl_content",
    "publish": "tbl_publish",
    "material": "tbl_material",
    "tag": "tbl_tag",
}

CURSOR_KEYS = [
    "feishu_sku",
    "feishu_plan",
    "feishu_prompt",
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
        init_engine(self.engine)
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

        self.assertEqual(len(fake.calls), 7)
        self.assertTrue(all(filter_str is not None for _, filter_str in fake.calls))
        self.assertTrue(any("Starting periodic hybrid sync of all tables" in line for line in logs.output))

    def test_periodic_hybrid_sync_forces_full_scan_on_configured_cadence(self):
        syncer, fake = self._make_syncer(mode="hybrid", full_every=2)

        syncer.sync_all(reason="periodic")
        fake.calls.clear()

        syncer.sync_all(reason="periodic")

        self.assertEqual(len(fake.calls), 7)
        self.assertTrue(all(filter_str is None for _, filter_str in fake.calls))
    def test_startup_sync_is_always_full_scan_even_in_hybrid_mode(self):
        syncer, fake = self._make_syncer(mode="hybrid", full_every=2)

        syncer.sync_all(reason="startup")

        self.assertEqual(len(fake.calls), 7)
        self.assertTrue(all(filter_str is None for _, filter_str in fake.calls))
    def test_plan_sync_reconciles_local_status_when_remote_record_is_completed(self):
        class PlanFeishu(FakeFeishu):
            def list_records(self, table_id: str, filter_str: str | None = None, page_size: int = 100):
                self.calls.append((table_id, filter_str))
                if table_id != TABLE_IDS["plan"]:
                    return []
                return [{
                    "record_id": "rec_plan_done",
                    "fields": {
                        "规划编号": "T_260507_109",
                        "任务名称": "得物9篇好物精选",
                        "任务类型": "AI全创作",
                        "内容类型": ["种草推荐"],
                        "目标平台": ["得物"],
                        "确认执行": "是",
                        "执行状态": "完成",
                        "任务完成时间": 1778209185628,
                        "任务日志": "完成时间: 2026-05-08 10:59:45\n共生成 5 条内容记录",
                    },
                }]

        fake = PlanFeishu()
        syncer = FeishuSyncer(fake, TABLE_IDS, engine=self.engine)

        with Session(self.engine) as session:
            session.add(Plan(
                feishu_record_id="rec_plan_done",
                plan_code="T_260507_109",
                task_name="得物9篇好物精选",
                task_type="AI全创作",
                exec_status="待执行",
                confirmed_exec=False,
            ))
            session.commit()

        syncer.sync_plans(run_mode="full_scan", reason="manual")

        with Session(self.engine) as session:
            plan = session.query(Plan).filter_by(plan_code="T_260507_109").one()
            self.assertEqual(plan.exec_status, "完成")
            self.assertTrue(plan.confirmed_exec)
            self.assertIsNotNone(plan.finished_at)
            self.assertIn("共生成 5 条内容记录", plan.error_msg or "")

    def test_content_sync_reconciles_local_status_when_remote_record_is_failed(self):
        class ContentFeishu(FakeFeishu):
            def list_records(self, table_id: str, filter_str: str | None = None, page_size: int = 100):
                self.calls.append((table_id, filter_str))
                if table_id != TABLE_IDS["content"]:
                    return []
                return [{
                    "record_id": "rec_content_failed",
                    "fields": {
                        "内容编号": "T_260507_109_img01",
                        "任务类型": "AI全创作",
                        "目标平台": "得物",
                        "内容类型": "种草推荐",
                        "内容形态": "图文",
                        "标题": None,
                        "正文": None,
                        "标签": None,
                        "素材文件夹路径": "D:/AI-Content-Hub/content-store/Pending_Content/T_260507_109/img01",
                        "生成时间": 1778209227151,
                        "生成状态": "生成失败",
                        "失败原因": "文案生成失败: Error code: 402 - Insufficient Balance",
                        "审核状态": "待审核",
                    },
                }]

        fake = ContentFeishu()
        syncer = FeishuSyncer(fake, TABLE_IDS, engine=self.engine)

        with Session(self.engine) as session:
            session.add(Content(
                feishu_record_id="rec_content_failed",
                content_code="T_260507_109_img01",
                task_type="AI全创作",
                target_platform="得物",
                content_type="种草推荐",
                content_form="图文",
                gen_status="生成中",
                review_status="待审核",
            ))
            session.commit()

        syncer.sync_contents(run_mode="full_scan", reason="manual")

        with Session(self.engine) as session:
            content = session.query(Content).filter_by(content_code="T_260507_109_img01").one()
            self.assertEqual(content.gen_status, "生成失败")
            self.assertIn("Insufficient Balance", content.error_msg or "")

    def test_prompt_sync_imports_prompt_rows_and_resolves_plan_fk(self):
        class PromptFeishu(FakeFeishu):
            def list_records(self, table_id: str, filter_str: str | None = None, page_size: int = 100):
                self.calls.append((table_id, filter_str))
                if table_id != TABLE_IDS["prompt"]:
                    return []
                return [{
                    "record_id": "rec_prompt_1",
                    "fields": {
                        "提示词编号": "P_T_260507_109_img01_C",
                        "关联规划": [{"record_id": "rec_plan_done"}],
                        "组号": "img01",
                        "Prompt类型": "图文正文",
                        "总Prompt": "[SYS]\\nfoo\\n[USR]\\nbar",
                        "子Prompt列表": None,
                        "版本号": 1,
                        "生成来源": "AI自动生成",
                        "使用模型": "gpt-5.4",
                        "状态": "已使用",
                    },
                }]

        fake = PromptFeishu()
        syncer = FeishuSyncer(fake, TABLE_IDS, engine=self.engine)

        with Session(self.engine) as session:
            session.add(Plan(
                feishu_record_id="rec_plan_done",
                plan_code="T_260507_109",
                task_name="得物9篇好物精选",
                task_type="AI全创作",
                exec_status="完成",
                confirmed_exec=True,
            ))
            session.commit()

        syncer.sync_prompts(run_mode="full_scan", reason="manual")

        with Session(self.engine) as session:
            prompt = session.query(Prompt).filter_by(prompt_code="P_T_260507_109_img01_C").one()
            plan = session.query(Plan).filter_by(plan_code="T_260507_109").one()
            self.assertEqual(prompt.feishu_record_id, "rec_prompt_1")
            self.assertEqual(prompt.plan_id, plan.id)
            self.assertEqual(prompt.group_id, "img01")
            self.assertEqual(prompt.prompt_type, "图文正文")
            self.assertEqual(prompt.model_used, "gpt-5.4")
            self.assertEqual(prompt.status, "已使用")
            self.assertIn("[SYS]", prompt.master_prompt or "")

    def test_update_content_status_persists_and_clears_error_message(self):
        with Session(self.engine) as session:
            session.add(Content(
                feishu_record_id="rec_content_local",
                content_code="T_260507_109_img99",
                task_type="AI全创作",
                target_platform="得物",
                content_type="种草推荐",
                content_form="图文",
                gen_status="生成中",
                review_status="待审核",
            ))
            session.commit()

        update_content_status(
            "T_260507_109_img99",
            gen_status="生成失败",
            error_msg="文案生成失败: Error code: 402 - Insufficient Balance",
        )

        with Session(self.engine) as session:
            content = session.query(Content).filter_by(content_code="T_260507_109_img99").one()
            self.assertEqual(content.gen_status, "生成失败")
            self.assertIn("Insufficient Balance", content.error_msg or "")

        update_content_status(
            "T_260507_109_img99",
            gen_status="生成中",
            error_msg=None,
        )

        with Session(self.engine) as session:
            content = session.query(Content).filter_by(content_code="T_260507_109_img99").one()
            self.assertEqual(content.gen_status, "生成中")
            self.assertIsNone(content.error_msg)


if __name__ == "__main__":
    unittest.main()
