from __future__ import annotations

import time
from loguru import logger

from .base_driver import BaseDriver


class AndroidDriver(BaseDriver):
    """UIAutomator2 驱动，适用于 Android 设备（含小米 MIUI）"""

    def __init__(self, server_url: str, caps: dict, timeout: int = 60):
        super().__init__(server_url, caps, timeout)
        self._screen_size: tuple[int, int] | None = None

    def connect(self) -> None:
        super().connect()
        size = self.driver.get_window_size()
        self._screen_size = (size["width"], size["height"])
        logger.info(f"Android 屏幕尺寸: {self._screen_size[0]}×{self._screen_size[1]}")
        # 连接后先清理可能存在的系统/MIUI 弹窗
        self._dismiss_miui_dialogs()

    @property
    def width(self) -> int:
        return self._screen_size[0] if self._screen_size else 1080

    @property
    def height(self) -> int:
        return self._screen_size[1] if self._screen_size else 2400

    # ──────────────────────────── scroll ────────────────────────────────

    def scroll_down(self, distance: int = 800) -> None:
        """手指上滑（内容下滚）"""
        cx = self.width // 2
        start_y = int(self.height * 0.75)
        end_y = max(start_y - distance, 100)
        self.driver.swipe(cx, start_y, cx, end_y, duration=500)
        time.sleep(0.3)

    def scroll_up(self, distance: int = 800) -> None:
        cx = self.width // 2
        start_y = int(self.height * 0.25)
        end_y = min(start_y + distance, self.height - 100)
        self.driver.swipe(cx, start_y, cx, end_y, duration=500)
        time.sleep(0.3)

    def scroll_in_element(self, element, direction: str = "down") -> None:
        """在指定容器内滚动"""
        loc = element.location
        size = element.size
        cx = loc["x"] + size["width"] // 2
        if direction == "down":
            start_y = loc["y"] + int(size["height"] * 0.75)
            end_y = loc["y"] + int(size["height"] * 0.25)
        else:
            start_y = loc["y"] + int(size["height"] * 0.25)
            end_y = loc["y"] + int(size["height"] * 0.75)
        self.driver.swipe(cx, start_y, cx, end_y, duration=500)
        time.sleep(0.3)

    def fling_to_top(self) -> None:
        """快速滑到顶部"""
        for _ in range(5):
            self.scroll_up(distance=self.height)
            time.sleep(0.2)

    # ──────────────────────────── app lifecycle ─────────────────────────

    def launch_app(self, package: str, activity: str = "") -> None:
        logger.info(f"启动 App: {package}")
        if activity:
            self.driver.start_activity(package, activity)
        else:
            self.driver.activate_app(package)
        time.sleep(3)
        self._dismiss_miui_dialogs()

    def terminate_app(self, package: str) -> None:
        self.driver.terminate_app(package)
        time.sleep(1)

    # ──────────────────────────── keyboard ──────────────────────────────

    def hide_keyboard(self) -> None:
        try:
            if self.driver.is_keyboard_shown():
                self.driver.hide_keyboard()
        except Exception:
            # 备用：按 Back 键收起键盘
            try:
                self.driver.press_keycode(4)  # KEYCODE_BACK
            except Exception:
                pass

    def press_enter(self) -> None:
        self.driver.press_keycode(66)  # KEYCODE_ENTER

    def press_search_key(self) -> None:
        self.driver.press_keycode(84)  # KEYCODE_SEARCH

    def press_back(self) -> None:
        self.driver.press_keycode(4)

    # ──────────────────────────── element text ──────────────────────────

    def element_text(self, element) -> str:
        for attr in ("text", "content-desc", "resource-id"):
            try:
                v = element.get_attribute(attr)
                if v and v.strip():
                    return v.strip()
            except Exception:
                pass
        return element.text or ""

    # ──────────────────────────── UIAutomator selectors ─────────────────

    def find_by_uia(self, selector: str, timeout: int = 10):
        """用 UIAutomator 字符串定位，如 'new UiSelector().text(\"搜索\")'"""
        from appium.webdriver.common.appiumby import AppiumBy
        from selenium.webdriver.support.wait import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        wait = WebDriverWait(self.driver, timeout)
        return wait.until(EC.presence_of_element_located(
            (AppiumBy.ANDROID_UIAUTOMATOR, selector)
        ))

    def find_all_by_uia(self, selector: str) -> list:
        from appium.webdriver.common.appiumby import AppiumBy
        return self.driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR, selector)

    def find_by_text(self, text: str, timeout: int = 10):
        return self.find_by_uia(f'new UiSelector().text("{text}")', timeout)

    def find_by_text_contains(self, text: str, timeout: int = 10):
        return self.find_by_uia(f'new UiSelector().textContains("{text}")', timeout)

    def find_by_desc(self, desc: str, timeout: int = 10):
        return self.find_by_uia(f'new UiSelector().description("{desc}")', timeout)

    def find_by_res_id_pattern(self, pattern: str, timeout: int = 10):
        return self.find_by_uia(f'new UiSelector().resourceIdMatches("{pattern}")', timeout)

    # ──────────────────────────── MIUI 弹窗处理 ──────────────────────────

    def _dismiss_miui_dialogs(self) -> None:
        """
        处理小米 MIUI 常见弹窗：
        - 自启动权限提示
        - 网络权限弹窗
        - 通知权限弹窗
        - 广告弹窗（"跳过"按钮）
        """
        dismiss_texts = [
            "取消", "拒绝", "不允许", "跳过", "暂不", "以后再说",
            "始终拒绝", "不再提示", "关闭", "Cancel", "Deny",
        ]
        for _ in range(3):
            dismissed = False
            for txt in dismiss_texts:
                el = self.try_find("xpath",
                    f'//*[@text="{txt}" or @content-desc="{txt}"]')
                if el:
                    try:
                        el.click()
                        logger.debug(f"关闭弹窗按钮: {txt}")
                        time.sleep(0.5)
                        dismissed = True
                        break
                    except Exception:
                        pass
            if not dismissed:
                break

    def dismiss_permission_popup(self) -> None:
        """处理 Android 系统权限弹窗"""
        for res_id in [
            "com.android.packageinstaller:id/permission_deny_button",
            "com.android.permissioncontroller:id/permission_deny_button",
        ]:
            el = self.try_find("id", res_id)
            if el:
                el.click()
                time.sleep(0.3)
                return
        self._dismiss_miui_dialogs()
