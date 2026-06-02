from __future__ import annotations

import time
from loguru import logger

from .base_driver import BaseDriver


class WindowsDriver(BaseDriver):
    """WinAppDriver 驱动，适用于 Windows 桌面应用"""

    def __init__(self, server_url: str, caps: dict, timeout: int = 60):
        super().__init__(server_url, caps, timeout)

    def scroll_down(self, distance: int = 800) -> None:
        size = self.driver.get_window_size()
        cx, cy = size["width"] // 2, size["height"] // 2
        self.driver.swipe(cx, cy + distance // 2, cx, cy - distance // 2, duration=500)
        time.sleep(0.5)

    def scroll_up(self, distance: int = 800) -> None:
        size = self.driver.get_window_size()
        cx, cy = size["width"] // 2, size["height"] // 2
        self.driver.swipe(cx, cy - distance // 2, cx, cy + distance // 2, duration=500)
        time.sleep(0.5)

    def launch_app(self, app_id: str) -> None:
        logger.info(f"启动 Windows 应用: {app_id}")
        try:
            self.driver.execute_script(f"ms:openApp {app_id}")
        except Exception:
            logger.warning("无法通过脚本启动应用，请手动确认应用已运行")
        time.sleep(3)

    def send_hotkey(self, *keys: str) -> None:
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        actions = ActionChains(self.driver)
        for k in keys[:-1]:
            actions.key_down(k)
        actions.send_keys(keys[-1])
        for k in reversed(keys[:-1]):
            actions.key_up(k)
        actions.perform()
