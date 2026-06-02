from __future__ import annotations

import time
from loguru import logger
from appium.webdriver.common.touch_action import TouchAction

from .base_driver import BaseDriver


class IOSDriver(BaseDriver):
    """XCUITest 驱动，适用于 iPhone/iPad"""

    def __init__(self, server_url: str, caps: dict, timeout: int = 60):
        super().__init__(server_url, caps, timeout)
        self._screen_size: tuple[int, int] | None = None

    def connect(self) -> None:
        super().connect()
        size = self.driver.get_window_size()
        self._screen_size = (size["width"], size["height"])
        logger.info(f"iOS 屏幕尺寸: {self._screen_size[0]}×{self._screen_size[1]}")

    @property
    def width(self) -> int:
        return self._screen_size[0] if self._screen_size else 390

    @property
    def height(self) -> int:
        return self._screen_size[1] if self._screen_size else 844

    # ──────────────────────────── scroll ────────────────────────────────

    def scroll_down(self, distance: int = 800) -> None:
        """手指上滑（内容下滚）"""
        cx = self.width // 2
        start_y = int(self.height * 0.75)
        end_y = max(start_y - distance, 50)
        self.driver.swipe(cx, start_y, cx, end_y, duration=600)
        time.sleep(0.5)

    def scroll_up(self, distance: int = 800) -> None:
        cx = self.width // 2
        start_y = int(self.height * 0.25)
        end_y = min(start_y + distance, self.height - 50)
        self.driver.swipe(cx, start_y, cx, end_y, duration=600)
        time.sleep(0.5)

    def scroll_to_top(self) -> None:
        """轻触状态栏回到顶部（iOS 特有手势）"""
        self.driver.execute_script(
            "mobile: scroll", {"direction": "up", "toVisible": True}
        )

    # ──────────────────────────── app lifecycle ─────────────────────────

    def launch_app(self, bundle_id: str) -> None:
        logger.info(f"启动 App: {bundle_id}")
        self.driver.activate_app(bundle_id)
        time.sleep(3)

    def terminate_app(self, bundle_id: str) -> None:
        self.driver.terminate_app(bundle_id)
        time.sleep(1)

    # ──────────────────────────── keyboard ──────────────────────────────

    def send_keys_via_keyboard(self, text: str) -> None:
        """逐字输入，绕过某些 App 对 send_keys 的拦截"""
        for char in text:
            self.driver.execute_script("mobile: type", {"text": char})
            time.sleep(0.05)

    # ──────────────────────────── element text ──────────────────────────

    def element_label(self, element) -> str:
        for attr in ("label", "value", "name"):
            try:
                v = element.get_attribute(attr)
                if v:
                    return v
            except Exception:
                pass
        return element.text or ""

    # ──────────────────────────── long press / tap ───────────────────────

    def long_press(self, element, duration_ms: int = 1500) -> None:
        action = TouchAction(self.driver)
        action.long_press(el=element, duration=duration_ms).release().perform()

    # ──────────────────────────── alerts ────────────────────────────────

    def dismiss_alert(self) -> bool:
        """处理系统弹窗（通知/定位权限等）"""
        try:
            alert = self.driver.switch_to.alert
            alert.dismiss()
            logger.debug("已关闭系统弹窗")
            return True
        except Exception:
            return False

    def allow_alert(self) -> bool:
        try:
            alert = self.driver.switch_to.alert
            alert.accept()
            return True
        except Exception:
            return False
