from __future__ import annotations

import time
from loguru import logger
from appium.webdriver.common.appiumby import AppiumBy

from apps.base_app import BaseApp
from models.content_item import ContentItem
from utils.helpers import parse_count


class XiaohongshuApp(BaseApp):
    """小红书自动化（iOS & Android）"""

    platform_name = "iOS"   # 默认值；实际由 driver 类型覆盖
    app_name = "xiaohongshu"
    BUNDLE_IOS = "com.xingin.discover"
    PACKAGE_ANDROID = "com.xingin.discover"
    ACTIVITY_ANDROID = "com.xingin.discover.activity.SplashActivity"

    # ──────────────────────────── lifecycle ──────────────────────────────

    def open(self) -> None:
        if self.is_android:
            from drivers.android_driver import AndroidDriver
            assert isinstance(self.driver, AndroidDriver)
            self.driver.launch_app(self.PACKAGE_ANDROID, self.ACTIVITY_ANDROID)
        else:
            from drivers.ios_driver import IOSDriver
            assert isinstance(self.driver, IOSDriver)
            self.driver.launch_app(self.BUNDLE_IOS)
            self.driver.dismiss_alert()
        time.sleep(self.search_wait)

    # ──────────────────────────── search ─────────────────────────────────

    def search(self, keyword: str) -> bool:
        logger.debug(f"[XHS/{('Android' if self.is_android else 'iOS')}] 搜索: {keyword}")
        if self.is_android:
            return self._search_android(keyword)
        return self._search_ios(keyword)

    def _search_android(self, keyword: str) -> bool:
        drv = self.driver
        # 多种方式找搜索入口
        for by, val in [
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().description("搜索")'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceIdMatches(".*search.*")'),
            (AppiumBy.XPATH, '//*[@content-desc="搜索" or @text="搜索"]'),
        ]:
            el = drv.try_find(by, val)
            if el:
                el.click()
                break
        else:
            logger.warning("[XHS] Android: 未找到搜索入口")
            return False

        time.sleep(1.0)

        # 输入框
        field = None
        for by, val in [
            (AppiumBy.CLASS_NAME, "android.widget.EditText"),
            (AppiumBy.XPATH, '//android.widget.EditText'),
        ]:
            field = drv.try_find(by, val)
            if field:
                break
        if not field:
            logger.warning("[XHS] Android: 未找到输入框")
            return False

        field.clear()
        field.send_keys(keyword)
        time.sleep(0.5)

        # 按搜索键
        from drivers.android_driver import AndroidDriver
        assert isinstance(drv, AndroidDriver)
        drv.press_search_key()
        time.sleep(self.result_wait)
        return True

    def _search_ios(self, keyword: str) -> bool:
        drv = self.driver
        for by, val in [
            ("accessibility id", "搜索"),
            ("xpath", '//XCUIElementTypeButton[@name="搜索"]'),
        ]:
            el = drv.try_find(by, val)
            if el:
                el.click()
                break
        else:
            return False

        time.sleep(1.0)
        field = drv.try_find("class name", "XCUIElementTypeTextField")
        if not field:
            return False
        field.clear()
        field.send_keys(keyword)
        time.sleep(0.5)
        drv.hide_keyboard()
        time.sleep(self.result_wait)
        return True

    # ──────────────────────────── collection ─────────────────────────────

    def collect_items(self, keyword: str, max_count: int) -> list[ContentItem]:
        items: list[ContentItem] = []
        seen: set[str] = set()
        scrolls = 0

        while len(items) < max_count and scrolls < 25:
            cells = self._find_cells()
            logger.debug(f"[XHS] 屏幕 {len(cells)} 个 cell，已采集 {len(items)}")
            for cell in cells:
                if len(items) >= max_count:
                    break
                item = self._parse_cell(cell, keyword, len(items) + 1, seen)
                if item:
                    items.append(item)
                    seen.add(item.title)
            if len(items) >= max_count:
                break
            self.driver.scroll_down()
            time.sleep(self.scroll_pause)
            scrolls += 1

        return items

    def _find_cells(self) -> list:
        if self.is_android:
            selectors = [
                (AppiumBy.XPATH, '//androidx.recyclerview.widget.RecyclerView/android.view.ViewGroup'),
                (AppiumBy.XPATH, '//android.widget.FrameLayout[@clickable="true"]'),
            ]
        else:
            selectors = [
                (AppiumBy.CLASS_NAME, "XCUIElementTypeCell"),
            ]
        for by, val in selectors:
            cells = self.driver.driver.find_elements(by, val)
            if cells:
                return cells
        return []

    def _parse_cell(self, cell, keyword: str, rank: int,
                    seen: set[str]) -> ContentItem | None:
        texts = self.extractor.texts_from_children(
            cell,
            by="class name",
            value="android.widget.TextView" if self.is_android else "XCUIElementTypeStaticText",
        )
        if not texts:
            return None
        title = texts[0]
        if not title or title in seen:
            return None

        author = texts[1] if len(texts) > 1 else ""
        stats = self.extractor.parse_stats_from_texts(texts[2:])
        ss_path = self._item_screenshot(cell, keyword, rank)

        item = ContentItem(
            rank=rank,
            platform="小红书",
            keyword=keyword,
            title=title,
            author=author,
            likes=stats["likes"],
            comments=stats["comments"],
            collects=stats["collects"],
            content_type="video" if self._is_video(texts) else "image",
            tags=self.extractor.extract_tags(" ".join(texts)),
            screenshot_path=ss_path,
        )
        item.compute_engagement()
        return item

    @staticmethod
    def _is_video(texts: list[str]) -> bool:
        return any(k in " ".join(texts) for k in ["视频", "video", "▶"])
