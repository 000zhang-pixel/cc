"""
LocalStorage — manages the local file system for AI-generated content.

Directory layout (platform-independent, root configured via LOCAL_STORAGE_ROOT env):

  {root}/                              ← Windows: D:/AI-Content-Hub/content-store
  │                                       Mac:     ~/openclaw/workspace/content-store
  ├── inbox/                           ← 原始素材输入区（用户手动放入）
  │   └── {sku_code}_{date}/           ← 例: SKU002_20260404
  │       └── {batch}/                 ← 例: post01, post02
  │           └── DSC001.jpg …
  │
  ├── Pending_Content/                 ← 生成内容工作区（系统读写，发布引擎读取）
  │   └── {plan_code}/                 ← 例: T_260404_020
  │       ├── plan.json
  │       ├── img01/                   ← 图文帖
  │       │   ├── content.json         ← 元数据 + 状态追踪
  │       │   ├── title.txt            ← 发布引擎直接读取
  │       │   ├── body_tags.txt        ← 发布引擎直接读取
  │       │   └── img_01.jpg … img_N.jpg
  │       └── vid01/                   ← 视频帖
  │           ├── content.json
  │           ├── title.txt
  │           ├── body_tags.txt
  │           └── video.mp4
  │
  └── archive/                         ← 发布归档区（发布成功后自动从 Pending_Content 移入）
      └── {year_month}/                ← 例: 2026-04
          └── {plan_code}/{group_id}/

Status flow (content.json "status" field):
  generated → review_passed → queued → published → [archived to archive/]
                                     ↘ publish_failed  (Pending_Content 保留，可重试)
"""
import json
import logging
import os
import platform
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Platform-specific default roots — overridden by LOCAL_STORAGE_ROOT env var
_DEFAULT_ROOTS = {
    "Windows": "D:/AI-Content-Hub/content-store",
    "Darwin":  str(Path.home() / "openclaw/workspace/content-store"),
    "Linux":   str(Path.home() / "AI-Content-Hub/content-store"),
}


def _default_root() -> str:
    return _DEFAULT_ROOTS.get(platform.system(), _DEFAULT_ROOTS["Linux"])


class LocalStorage:
    def __init__(self, root: str | None = None):
        """
        root: override path (from config/env). If None, falls back to platform default.
        Always prefer injecting via LOCAL_STORAGE_ROOT env var or system.yaml.
        """
        resolved = root or os.environ.get("LOCAL_STORAGE_ROOT") or _default_root()
        self.root = Path(resolved)
        self.inbox   = self.root / "inbox"
        self.pending = self.root / "Pending_Content"
        self.archive = self.root / "archive"

    # ------------------------------------------------------------------
    # Plan-level
    # ------------------------------------------------------------------

    def save_plan(self, plan_code: str, plan_meta: dict) -> Path:
        """Write plan.json under Pending_Content/{plan_code}/."""
        plan_dir = self.pending / plan_code
        plan_dir.mkdir(parents=True, exist_ok=True)
        path = plan_dir / "plan.json"
        path.write_text(
            json.dumps({**plan_meta, "plan_code": plan_code}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("Saved plan.json → %s", path)
        return path

    def update_plan(self, plan_code: str, updates: dict) -> None:
        """Merge `updates` into existing plan.json (read-modify-write)."""
        path = self.pending / plan_code / "plan.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"plan_code": plan_code}
        existing.update(updates)
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("Updated plan.json → %s", path)

    # ------------------------------------------------------------------
    # Content-unit operations
    # ------------------------------------------------------------------

    def save_content(
        self,
        plan_code: str,
        group_id: str,
        meta: dict,
        files: dict,   # filename → bytes
    ) -> Path:
        """Write content.json, title.txt, body_tags.txt, and binary files."""
        group_dir = self.pending / plan_code / group_id
        group_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat(timespec="seconds")
        images = sorted(k for k in files if k.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
        videos = sorted(k for k in files if k.lower().endswith((".mp4", ".mov", ".avi", ".mkv")))

        content_data = {
            "content_code":     meta.get("content_code", f"{plan_code}_{group_id}"),
            "plan_code":        plan_code,
            "group_id":         group_id,
            "feishu_record_id": meta.get("feishu_record_id", ""),
            "platform":         meta.get("platform", ""),
            "content_type":     meta.get("content_type", ""),
            "content_form":     meta.get("content_form", ""),
            "title":            meta.get("title", ""),
            "body":             meta.get("body", ""),
            "tags":             meta.get("tags", ""),
            "images":           images,
            "video":            videos[0] if videos else None,
            "status":           "generated",
            "created_at":       now,
            "updated_at":       now,
        }

        (group_dir / "content.json").write_text(
            json.dumps(content_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (group_dir / "title.txt").write_text(content_data["title"].strip(), encoding="utf-8")
        body_tags = f"{content_data['body'].strip()}\n\n{content_data['tags'].strip()}"
        (group_dir / "body_tags.txt").write_text(body_tags.strip(), encoding="utf-8")

        for filename, data in files.items():
            if data:
                (group_dir / filename).write_bytes(data)

        logger.info("LocalStorage: saved %s", content_data["content_code"])
        return group_dir

    def update_text(self, plan_code: str, group_id: str, title: str, body: str, tags: str) -> None:
        """Overwrite title.txt / body_tags.txt and update text fields in content.json."""
        group_dir = self.pending / plan_code / group_id
        group_dir.mkdir(parents=True, exist_ok=True)

        (group_dir / "title.txt").write_text(title.strip(), encoding="utf-8")
        (group_dir / "body_tags.txt").write_text(
            f"{body.strip()}\n\n{tags.strip()}".strip(), encoding="utf-8"
        )

        json_path = group_dir / "content.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            data.update({"title": title, "body": body, "tags": tags,
                         "updated_at": datetime.now().isoformat(timespec="seconds")})
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_file(self, plan_code: str, group_id: str, filename: str, data: bytes) -> Path:
        """Save a single binary file and update the file list in content.json."""
        group_dir = self.pending / plan_code / group_id
        group_dir.mkdir(parents=True, exist_ok=True)
        dest = group_dir / filename
        dest.write_bytes(data)

        json_path = group_dir / "content.json"
        if json_path.exists():
            content_data = json.loads(json_path.read_text(encoding="utf-8"))
            if filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                imgs = set(content_data.get("images") or [])
                imgs.add(filename)
                content_data["images"] = sorted(imgs)
            elif filename.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
                content_data["video"] = filename
            content_data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            json_path.write_text(
                json.dumps(content_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        logger.debug("LocalStorage: added file %s → %s", filename, group_dir)
        return dest

    def update_status(self, plan_code: str, group_id: str, status: str) -> None:
        """Update the status field in content.json."""
        path = self.pending / plan_code / group_id / "content.json"
        if not path.exists():
            logger.warning("update_status: content.json not found at %s", path)
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = status
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_content_path(self, plan_code: str, group_id: str) -> Path:
        return self.pending / plan_code / group_id

    def read_content_meta(self, plan_code: str, group_id: str) -> dict | None:
        path = self.pending / plan_code / group_id / "content.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Archive — move published content out of Pending_Content
    # ------------------------------------------------------------------

    def archive_content(self, plan_code: str, group_id: str) -> Path | None:
        """
        Move Pending_Content/{plan_code}/{group_id}/ → archive/{year_month}/{plan_code}/{group_id}/.
        Called after a successful publish. Returns the archive path, or None if source missing.
        """
        src = self.pending / plan_code / group_id
        if not src.exists():
            logger.warning("archive_content: source not found %s", src)
            return None

        year_month = datetime.now().strftime("%Y-%m")
        dest = self.archive / year_month / plan_code / group_id
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        logger.info("Archived %s/%s → %s", plan_code, group_id, dest)

        # Clean up empty plan dir (keep plan.json if other groups remain)
        plan_dir = self.pending / plan_code
        try:
            remaining = [p for p in plan_dir.iterdir() if p.name != "plan.json"]
            if not remaining:
                plan_dir.rmdir()
        except Exception:
            pass

        return dest

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_queued(self, platform: str | None = None) -> list[dict]:
        return self._scan_pending(status="queued", platform=platform)

    def list_by_status(self, status: str) -> list[dict]:
        return self._scan_pending(status=status)

    def _scan_pending(self, status: str, platform: str | None = None) -> list[dict]:
        results = []
        for json_path in self.pending.rglob("content.json"):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("status") != status:
                continue
            if platform and data.get("platform") != platform:
                continue
            data["local_path"] = str(json_path.parent)
            results.append(data)
        return results
