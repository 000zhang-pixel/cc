"""
PublishHandler — processes a 表5 发布执行表 record.

Workflow:
  1. Read 表5 record → get content_code, 发布方式
  2. Find local workspace content via LocalStorage
  3. Pass workspace dir directly to publish_engine.sh via CONTENT_WORKSPACE_DIR env var
  4. Call bash publish_engine.sh single <pub_id> <content_id>
  5. Update 表5 发布状态 based on exit code
  6. On success: archive content from Pending_Content/ → archive/{year_month}/

Workspace layout (read directly, no copying):
  {LOCAL_STORAGE_ROOT}/Pending_Content/{plan_code}/{group_id}/
    img_01.jpg ~ img_05.jpg
    title.txt
    body_tags.txt

支持的发布方式（可在 system.yaml publish.methods 中配置）:
  - "立即发布" + 目标平台含"得物" → calls dewu.engine_script
  - "得物自动发布"                 → same (legacy compat)
  - 其他任何非待定值               → 手动发布占位（仅写 已发布 状态）
"""
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from adapters.feishu import FeishuClient
from core.local_storage import LocalStorage
from core.task import Task

logger = logging.getLogger(__name__)


class PublishHandler:
    def __init__(
        self,
        feishu: FeishuClient,
        tables: dict,
        storage: LocalStorage | None,
        publish_cfg: dict,   # from system.yaml publish section
        notifications_cfg: dict | None = None,
    ):
        self._feishu = feishu
        self._tables = tables
        self._storage = storage
        self._cfg = publish_cfg   # {"dewu": {...}, "xiaohongshu": {...}, ...}
        self._notifications = notifications_cfg or {}

    def __call__(self, task: Task):
        record_id = task.record_id
        table_publish = self._tables["publish"]
        try:
            self._run(record_id)
        except Exception as exc:
            logger.exception("PublishHandler failed for record %s", record_id)
            try:
                self._feishu.update_record(table_publish, record_id, {
                    "发布状态": "发布失败",
                    "备注": str(exc)[:500],
                })
            except Exception:
                pass
            # Enrich failure card: read pub + content record (best-effort)
            pub_code = record_id[:8]
            platform = form_type = sku_name = title_preview = ""
            try:
                rec = self._feishu.get_record(table_publish, record_id)
                pub_code = self._feishu.get_text(rec, "发布编号").strip() or pub_code
                content_ids = self._feishu.get_link_ids(rec, "关联内容")
                if content_ids:
                    table_content = self._tables["content"]
                    c_rec = self._feishu.get_record(table_content, content_ids[0])
                    platform = self._feishu.get_option(c_rec, "目标平台") or ""
                    form_type = self._feishu.get_option(c_rec, "内容形态") or ""
                    title_preview = self._feishu.get_text(c_rec, "标题").strip()[:30]
                    sku_ids = self._feishu.get_link_ids(c_rec, "关联SKU")
                    if sku_ids and self._tables.get("sku"):
                        s_rec = self._feishu.get_record(self._tables["sku"], sku_ids[0])
                        sku_name = self._feishu.get_text(s_rec, "SKU名称").strip()
            except Exception:
                pass
            self._notify_card_failure(pub_code, platform, form_type, sku_name, title_preview, str(exc)[:120])
            # SKU stats
            try:
                self._update_sku_stats(record_id)
            except Exception:
                logger.warning("[SKUStats] update failed after publish failure", exc_info=True)

    # ------------------------------------------------------------------

    def _run(self, pub_record_id: str):
        f = self._feishu
        table_publish = self._tables["publish"]
        table_content = self._tables["content"]

        # 1. Read 表5 record
        pub_rec = f.get_record(table_publish, pub_record_id)
        publish_method = f.get_option(pub_rec, "发布方式")
        pub_code = f.get_text(pub_rec, "发布编号").strip() or pub_record_id[:8]

        # 2. Get linked content record
        content_ids = f.get_link_ids(pub_rec, "关联内容")
        if not content_ids:
            raise ValueError("表5记录缺少关联内容")
        content_rec = f.get_record(table_content, content_ids[0])
        content_code = f.get_text(content_rec, "内容编号").strip()
        if not content_code:
            raise ValueError(f"关联内容记录 {content_ids[0]} 缺少内容编号")

        # 3. Parse plan_code + group_id from content_code
        plan_code, group_id = _parse_content_code(content_code)
        logger.info("[Publish] %s → plan=%s group=%s method=%s",
                    content_code, plan_code, group_id, publish_method)

        # 4. Read local workspace path
        workspace_dir: Path | None = None
        if self._storage:
            workspace_dir = self._storage.get_content_path(plan_code, group_id)

        # 5. Dispatch by platform / publish method
        platform = f.get_option(content_rec, "目标平台") or ""

        if (publish_method == "立即发布" and "得物" in platform) or publish_method == "得物自动发布":
            # Mark 发布中 HERE — before any further work, so the poller won't re-queue
            # this record while we validate workspace / run the engine.
            f.update_record(table_publish, pub_record_id, {"发布状态": "发布中"})
            self._publish_dewu(
                pub_record_id, pub_code, content_code, workspace_dir, content_rec,
            )
        else:
            # Any other non-待定 value → manual placeholder
            logger.info("[Publish] method=%r — no automation, marking 已发布", publish_method)
            f.update_record(table_publish, pub_record_id, {
                "发布状态": "已发布",
                "实际发布时间": int(datetime.now().timestamp() * 1000),
            })
            if self._storage and plan_code and group_id:
                try:
                    self._storage.update_status(plan_code, group_id, "published")
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 得物 ADB 自动发布
    # ------------------------------------------------------------------

    def _publish_dewu(
        self,
        pub_record_id: str,
        pub_code: str,
        content_code: str,
        workspace_dir: Path | None,
        content_rec: dict | None = None,
    ):
        f = self._feishu
        table_publish = self._tables["publish"]
        dewu_cfg = self._cfg.get("dewu", {})

        engine_script = dewu_cfg.get("engine_script", "").strip()
        if not engine_script:
            raise ValueError(
                "publish.dewu.engine_script 未配置 — 请在 system.yaml 中填入 publish_engine 脚本路径"
            )

        # Ensure workspace exists; if it's already archived, treat as already published
        if workspace_dir is None or not workspace_dir.exists():
            archived_path = None
            if self._storage and workspace_dir is not None:
                import glob as _glob
                parts = workspace_dir.parts
                if len(parts) >= 2:
                    plan_part = parts[-2]
                    group_part = parts[-1]
                    pattern = str(self._storage.archive / "*" / plan_part / group_part)
                    matches = _glob.glob(pattern)
                    if matches:
                        archived_path = matches[0]
            if archived_path:
                logger.warning(
                    "[Publish] workspace already archived at %s — marking 已发布 without re-running",
                    archived_path,
                )
                f.update_record(table_publish, pub_record_id, {
                    "发布状态": "已发布",
                    "实际发布时间": int(datetime.now().timestamp() * 1000),
                    "备注": "内容已归档，本次跳过重复发布",
                })
                return
            raise ValueError(
                f"本地工作区不存在: {workspace_dir} — 请先生成内容"
            )

        # Pass workspace path in Windows forward-slash format (D:/...) — adb can read it,
        # and Git Bash won't mangle it (only /drive/... paths get converted).
        win_workspace = str(workspace_dir).replace("\\", "/")
        logger.info("[Publish] workspace path: %s", win_workspace)

        # Build env — ensure bash and adb are findable
        extra_paths = [r"C:\Program Files\Git\usr\bin", r"C:\platform-tools"]
        existing_path = os.environ.get("PATH", "")
        for p in extra_paths:
            if p not in existing_path:
                existing_path = existing_path + os.pathsep + p
        env = {
            **os.environ,
            "CONTENT_WORKSPACE_DIR": win_workspace,
            "PATH": existing_path,
        }

        # On Windows, subprocess searches the PARENT process PATH for the executable,
        # not the child env PATH. Resolve bash explicitly from our constructed PATH.
        import shutil
        bash_exe = shutil.which("bash", path=existing_path) or "bash"
        cmd = [bash_exe, engine_script, "single", pub_code, content_code]
        logger.info("[Publish] Running: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,    # 10 minutes max
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("发布引擎超时（10分钟）")

        stdout_tail = (result.stdout or "")[-500:]
        stderr_tail = (result.stderr or "")[-500:]
        log_tail = stderr_tail or stdout_tail

        if result.returncode == 0:
            f.update_record(table_publish, pub_record_id, {
                "发布状态": "已发布",
                "实际发布时间": int(datetime.now().timestamp() * 1000),
            })
            if self._storage:
                try:
                    plan_code, group_id = _parse_content_code(content_code)
                    self._storage.update_status(plan_code, group_id, "published")
                    self._storage.archive_content(plan_code, group_id)
                except Exception:
                    logger.warning("[Publish] archive_content failed, workspace kept", exc_info=True)
            logger.info("[Publish] %s 发布成功", content_code)
            # Enrich success card
            platform = form_type = sku_name = title_preview = ""
            if content_rec:
                platform = f.get_option(content_rec, "目标平台") or ""
                form_type = f.get_option(content_rec, "内容形态") or ""
                title_preview = f.get_text(content_rec, "标题").strip()[:30]
                try:
                    sku_ids = f.get_link_ids(content_rec, "关联SKU")
                    if sku_ids and self._tables.get("sku"):
                        s_rec = f.get_record(self._tables["sku"], sku_ids[0])
                        sku_name = f.get_text(s_rec, "SKU名称").strip()
                except Exception:
                    pass
            self._notify_card_success(pub_code, platform, form_type, sku_name, title_preview, pub_record_id)
            try:
                self._update_sku_stats(pub_record_id)
            except Exception:
                logger.warning("[SKUStats] update failed after publish success", exc_info=True)
        else:
            raise RuntimeError(
                f"发布引擎退出码 {result.returncode}，最后500字:\n{log_tail}"
            )


    # ------------------------------------------------------------------
    # Notification helpers
    # ------------------------------------------------------------------

    def _notify_card_success(
        self, pub_code: str, platform: str, form_type: str,
        sku_name: str, title_preview: str, pub_record_id: str
    ) -> None:
        """Send a '发布成功' green card to the configured Feishu group."""
        if not self._notifications.get("enabled"):
            return
        if not self._notifications.get("notify_on", {}).get("success", True):
            return
        chat_id = self._notifications.get("chat_id", "").strip()
        if not chat_id:
            return
        pub_time = datetime.now().strftime("%m-%d %H:%M")
        # Compute stats for the footer (best-effort)
        stats_note = ""
        try:
            all_stats = self._get_sku_stats_summary(pub_record_id)
            if all_stats:
                stats_note = all_stats
        except Exception:
            pass
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"content": "✅ 发布成功", "tag": "plain_text"},
                "template": "green",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"content": f"**发布编号**\n{pub_code}", "tag": "lark_md"}},
                        {"is_short": True, "text": {"content": f"**目标平台**\n{platform or '得物'}", "tag": "lark_md"}},
                    ],
                },
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"content": f"**内容形态**\n{form_type or '—'}", "tag": "lark_md"}},
                        {"is_short": True, "text": {"content": f"**SKU**\n{sku_name or '—'}", "tag": "lark_md"}},
                    ],
                },
                {
                    "tag": "div",
                    "text": {"content": f"**标题预览**\n{title_preview or '—'}", "tag": "lark_md"},
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": f"发布时间：{pub_time}  {stats_note}"}],
                },
            ],
        }
        try:
            self._feishu.send_group_card(chat_id, card)
        except Exception as exc:
            logger.warning("[Notify] card send failed: %s", exc)

    def _notify_card_failure(
        self, pub_code: str, platform: str, form_type: str,
        sku_name: str, title_preview: str, reason: str
    ) -> None:
        """Send a '发布失败' red card to the configured Feishu group."""
        if not self._notifications.get("enabled"):
            return
        if not self._notifications.get("notify_on", {}).get("failure", True):
            return
        chat_id = self._notifications.get("chat_id", "").strip()
        if not chat_id:
            return
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"content": "❌ 发布失败", "tag": "plain_text"},
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"content": f"**发布编号**\n{pub_code}", "tag": "lark_md"}},
                        {"is_short": True, "text": {"content": f"**目标平台**\n{platform or '得物'}", "tag": "lark_md"}},
                    ],
                },
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"content": f"**内容形态**\n{form_type or '—'}", "tag": "lark_md"}},
                        {"is_short": True, "text": {"content": f"**SKU**\n{sku_name or '—'}", "tag": "lark_md"}},
                    ],
                },
                {
                    "tag": "div",
                    "text": {"content": f"**标题预览**\n{title_preview or '—'}", "tag": "lark_md"},
                },
                {
                    "tag": "div",
                    "text": {"content": f"**失败原因**\n{reason}", "tag": "lark_md"},
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "⚠️ 请检查本地工作区并手动处理，或重新触发发布"}],
                },
            ],
        }
        try:
            self._feishu.send_group_card(chat_id, card)
        except Exception as exc:
            logger.warning("[Notify] card send failed: %s", exc)

    def _get_sku_stats_summary(self, pub_record_id: str) -> str:
        """Return a short stats string like '累计发布 5 次' for the success card footer."""
        if "sku_stats" not in self._tables:
            return ""
        f = self._feishu
        table_publish = self._tables["publish"]
        table_content = self._tables["content"]
        table_stats = self._tables["sku_stats"]
        pub_rec = f.get_record(table_publish, pub_record_id)
        content_ids = f.get_link_ids(pub_rec, "关联内容")
        if not content_ids:
            return ""
        content_rec = f.get_record(table_content, content_ids[0])
        sku_ids = f.get_link_ids(content_rec, "关联SKU")
        if not sku_ids:
            return ""
        sku_record_id = sku_ids[0]
        all_stats = f.list_records(table_stats)
        for rec in all_stats:
            if sku_record_id in f.get_link_ids(rec, "关联SKU"):
                success = f.get_number(rec, "发布成功数", 0)
                return f"该SKU累计发布成功 {int(success)} 次"
        return ""

    # ------------------------------------------------------------------
    # SKU statistics helper
    # ------------------------------------------------------------------

    def _update_sku_stats(self, pub_record_id: str) -> None:
        """Recompute and write SKU statistics based on all publish records for the SKU."""
        if "sku_stats" not in self._tables:
            return
        f = self._feishu
        table_publish = self._tables["publish"]
        table_content = self._tables["content"]
        table_stats = self._tables["sku_stats"]

        # 1. Get content record linked from the publish record
        pub_rec = f.get_record(table_publish, pub_record_id)
        content_ids = f.get_link_ids(pub_rec, "关联内容")
        if not content_ids:
            return
        content_rec = f.get_record(table_content, content_ids[0])

        # 2. Get SKU record ID from content
        sku_ids = f.get_link_ids(content_rec, "关联SKU")
        if not sku_ids:
            return
        sku_record_id = sku_ids[0]

        # 3. Find all content records for this SKU
        all_content = f.list_records(table_content)
        sku_content_ids = set()
        for rec in all_content:
            if sku_record_id in f.get_link_ids(rec, "关联SKU"):
                sku_content_ids.add(rec["record_id"])
        total_content = len(sku_content_ids)

        # 4. Count publish outcomes for those content records
        success = fail = pending = 0
        latest_time_ms: int | None = None
        latest_pub_code = ""

        all_publish = f.list_records(table_publish)
        for rec in all_publish:
            linked = f.get_link_ids(rec, "关联内容")
            if not any(cid in sku_content_ids for cid in linked):
                continue
            status = f.get_option(rec, "发布状态")
            if status == "已发布":
                success += 1
                pub_time = f.get_field(rec, "实际发布时间")
                if pub_time and (latest_time_ms is None or int(pub_time) > latest_time_ms):
                    latest_time_ms = int(pub_time)
                    latest_pub_code = f.get_text(rec, "发布编号")
            elif status == "发布失败":
                fail += 1
            elif status in ("待发布", "发布中"):
                pending += 1

        # 5. Find the stats row for this SKU
        all_stats = f.list_records(table_stats)
        stats_record_id = None
        for rec in all_stats:
            if sku_record_id in f.get_link_ids(rec, "关联SKU"):
                stats_record_id = rec["record_id"]
                break
        if not stats_record_id:
            logger.warning("[SKUStats] No stats row for SKU %s", sku_record_id)
            return

        # 6. Write updated stats
        update_fields: dict = {
            "累计生成内容数": total_content,
            "发布成功数": success,
            "发布失败数": fail,
            "待发布数": pending,
            "最新发布内容": latest_pub_code,
        }
        if latest_time_ms is not None:
            update_fields["最新发布时间"] = latest_time_ms
        f.update_record(table_stats, stats_record_id, update_fields)
        logger.info(
            "[SKUStats] %s — content=%d ok=%d fail=%d pending=%d",
            sku_record_id, total_content, success, fail, pending,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_content_code(content_code: str) -> tuple[str, str]:
    """
    T_260404_016_img01 → ("T_260404_016", "img01")
    T_260404_016_vid01 → ("T_260404_016", "vid01")
    """
    for sep in ("_img", "_vid"):
        if sep in content_code:
            prefix, suffix = content_code.rsplit(sep, 1)
            return prefix, sep.lstrip("_") + suffix
    # fallback: split on last _
    parts = content_code.rsplit("_", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return content_code, ""
