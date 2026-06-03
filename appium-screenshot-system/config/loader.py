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
        ver = self.get("appium", "api_version", default="")
        return f"{base}{ver}"

    def ios_caps(self, bundle_id: str) -> dict:
        base = dict(self._settings.get("ios", {}))
        base["app"] = bundle_id
        base.setdefault("automationName", "XCUITest")
        return base

    def android_caps(self, package: str, activity: str = "") -> dict:
        """构建 Android UIAutomator2 capabilities（兼容 Appium 2.x W3C 格式）"""
        raw = dict(self._settings.get("android", {}))
        # W3C 格式要求 appium: 前缀的 capability 用 appium:xxx 键名
        caps: dict = {"platformName": raw.pop("platform_name", "Android")}
        rename = {
            "automation_name": "appium:automationName",
            "device_name": "appium:deviceName",
            "udid": "appium:udid",
            "platform_version": "appium:platformVersion",
            "no_reset": "appium:noReset",
            "full_reset": "appium:fullReset",
            "language": "appium:language",
            "locale": "appium:locale",
            "new_command_timeout": "appium:newCommandTimeout",
            "unicode_keyboard": "appium:unicodeKeyboard",
            "reset_keyboard": "appium:resetKeyboard",
            "disable_window_animation": "appium:disableWindowAnimation",
            "skip_device_initialization": "appium:skipDeviceInitialization",
            "auto_grant_permissions": "appium:autoGrantPermissions",
        }
        for k, v in raw.items():
            caps[rename.get(k, f"appium:{k}")] = v
        caps["appium:appPackage"] = package
        if activity:
            caps["appium:appActivity"] = activity
        caps["appium:noReset"] = caps.get("appium:noReset", True)
        # 去掉空字符串的 platformVersion（让 Appium 自动检测）
        if not caps.get("appium:platformVersion"):
            caps.pop("appium:platformVersion", None)
        return caps

    def windows_caps(self, app_id: str = "Root") -> dict:
        base = dict(self._settings.get("windows", {}))
        base["app"] = app_id
        return base

    def app_config(self, app_name: str) -> dict:
        return self._settings.get("apps", {}).get(app_name, {})

    def android_udid(self) -> str:
        return self.get("android", "udid", default="")

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
