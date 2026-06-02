from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml


class ConfigLoader:
    def __init__(self, settings_path: str = "config/settings.yaml",
                 keywords_path: str = "config/keywords.yaml"):
        self._settings = self._load(settings_path)
        self._keywords = self._load(keywords_path)

    @staticmethod
    def _load(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")
        with p.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self._settings
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, default)
        return node

    def appium_url(self) -> str:
        base = self.get("appium", "server_url", default="http://localhost:4723")
        ver = self.get("appium", "api_version", default="/wd/hub")
        return f"{base}{ver}"

    def ios_caps(self, bundle_id: str) -> dict:
        base = dict(self._settings.get("ios", {}))
        base["app"] = bundle_id
        base.setdefault("automationName", "XCUITest")
        return base

    def windows_caps(self, app_id: str = "Root") -> dict:
        base = dict(self._settings.get("windows", {}))
        base["app"] = app_id
        return base

    def app_config(self, app_name: str) -> dict:
        return self._settings.get("apps", {}).get(app_name, {})

    def keywords_for(self, app_name: str) -> list[str]:
        common = self._keywords.get("common", [])
        specific = self._keywords.get(app_name, [])
        priority = self._keywords.get("priority", [])
        seen: set[str] = set()
        result: list[str] = []
        for kw in priority + specific + common:
            if kw not in seen:
                seen.add(kw)
                result.append(kw)
        return result

    def screenshot_cfg(self) -> dict:
        return self._settings.get("screenshot", {})

    def ocr_cfg(self) -> dict:
        return self._settings.get("ocr", {})

    def sentiment_cfg(self) -> dict:
        return self._settings.get("sentiment", {})

    def output_cfg(self) -> dict:
        return self._settings.get("output", {})
