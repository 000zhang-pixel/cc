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
    ):
        self._feishu = feishu
        self._tables = tables
        self._storage = storage
        self._cfg = publish_cfg   # {"dewu": {...}, "xiaohongshu": {...}, ...}

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
                pub_record_id, pub_code, content_code, workspace_dir,
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
        else:
            raise RuntimeError(
                f"发布引擎退出码 {result.returncode}，最后500字:\n{log_tail}"
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
