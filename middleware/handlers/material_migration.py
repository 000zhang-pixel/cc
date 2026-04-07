"""
MaterialMigrationHandler — when 表4 确认搬迁=是,
copies files from the user-specified source folder into the workspace
content-unit directory and renames them for publishing order.

Source:  user-specified inbox subfolder  (e.g. D:/AI-Content-Hub/content-store/inbox/SKU002_20260404/post01/)
Target:  D:/AI-Content-Hub/content-store/Pending_Content/{plan_code}/{group_id}/
         (same directory that ContentGenerationHandler creates for AI-generated content)

Renaming convention:
  img_01.jpg, img_02.jpg …  (images)
  vid_01.mp4, vid_02.mp4 …  (video)

Files are sorted by natural order (DSC001 < DSC002 < DSC010 < DSC100).
"""
import logging
import re
import shutil
from pathlib import Path

from adapters.feishu import FeishuClient
from core.local_storage import LocalStorage
from core.task import Task

logger = logging.getLogger(__name__)


def _natural_key(path: Path):
    """Sort key that handles embedded numbers correctly: img2 < img10."""
    parts = re.split(r'(\d+)', path.name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def _parse_content_code(content_code: str) -> tuple[str, str]:
    """
    Split content_code into (plan_code, group_id).

    T_260404_010_img01  →  ('T_260404_010', 'img01')
    T_260404_010_vid01  →  ('T_260404_010', 'vid01')

    Falls back to (content_code, '') if pattern not matched.
    """
    m = re.match(r'^(T_\d{6}_\d+)_(img\d+|vid\d+)$', content_code)
    if m:
        return m.group(1), m.group(2)
    # Fallback: split at last underscore
    idx = content_code.rfind('_')
    if idx != -1:
        return content_code[:idx], content_code[idx + 1:]
    return content_code, ''


class MaterialMigrationHandler:
    def __init__(
        self,
        feishu: FeishuClient,
        tables: dict,
        local_storage: LocalStorage | None = None,
    ):
        self._feishu = feishu
        self._tables = tables
        self._storage = local_storage

    def __call__(self, task: Task):
        record_id = task.record_id
        table_content = self._tables["content"]
        f = self._feishu

        try:
            self._run(record_id)
        except Exception as exc:
            logger.exception("MaterialMigration failed for record %s", record_id)
            f.update_record(table_content, record_id, {
                "搬迁状态": "搬迁失败",
                "失败原因": str(exc),
            })

    def _run(self, record_id: str):
        f = self._feishu
        table_content = self._tables["content"]

        rec = f.get_record(table_content, record_id)

        src_path_str = f.get_text(rec, "素材文件夹路径").strip()
        content_code = f.get_text(rec, "内容编号").strip()
        content_form = f.get_option(rec, "内容形态")

        if not src_path_str:
            raise ValueError("素材文件夹路径为空")

        src_path = Path(src_path_str)
        if not src_path.exists():
            raise FileNotFoundError(f"源路径不存在: {src_path}")

        # Determine target directory
        plan_code, group_id = _parse_content_code(content_code)
        if self._storage and plan_code and group_id:
            target_dir = self._storage.get_content_path(plan_code, group_id)
        else:
            # Fallback: use Pending_Content directly
            target_dir = Path("D:/AI-Content-Hub/content-store/Pending_Content") / content_code

        target_dir.mkdir(parents=True, exist_ok=True)

        # Collect source files
        valid_ext_map = {
            "图文":   [".jpg", ".jpeg", ".png", ".webp"],
            "单图文": [".jpg", ".jpeg", ".png", ".webp"],
            "视频":   [".mp4", ".mov", ".avi", ".mkv"],
        }
        valid_exts = valid_ext_map.get(content_form, [])
        is_video = content_form == "视频"

        if src_path.is_dir():
            candidates = [p for p in src_path.iterdir() if p.is_file()]
        else:
            candidates = [src_path]

        if valid_exts:
            candidates = [p for p in candidates if p.suffix.lower() in valid_exts]

        if not candidates:
            raise ValueError(
                f"源路径中没有符合格式的文件（期望: {valid_exts}）: {src_path}"
            )

        # Natural sort to preserve photographer's intended sequence
        candidates = sorted(candidates, key=_natural_key)

        prefix = "vid" if is_video else "img"
        copied = 0
        for idx, file in enumerate(candidates, start=1):
            new_name = f"{prefix}_{idx:02d}{file.suffix.lower()}"
            dest = target_dir / new_name
            shutil.copy2(file, dest)
            copied += 1
            logger.debug("Copied %s → %s", file.name, dest.name)

            # Register file in content.json (best-effort)
            if self._storage and plan_code and group_id:
                try:
                    self._storage.add_file(plan_code, group_id, new_name, dest.read_bytes())
                except Exception:
                    logger.warning(
                        "LocalStorage add_file failed for %s", new_name, exc_info=True
                    )

        # Write back: update source path → target path, mark complete
        f.update_record(table_content, record_id, {
            "素材文件夹路径": str(target_dir),
            "搬迁状态": "已完成",
        })
        logger.info(
            "MaterialMigration complete for %s: %d file(s) → %s",
            content_code, copied, target_dir,
        )
