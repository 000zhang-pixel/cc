from __future__ import annotations

import time
from loguru import logger
from appium.webdriver.common.appiumby import AppiumBy

from apps.base_app import BaseApp
from models.content_item import ContentItem


class DouyinApp(BaseApp):
    """抖音自动化（iOS & Android）"""

    platform_name = "iOS"
    app_name = "douyin"
    BUNDLE_IOS = "com.ss.iphone.ugc.Aweme"
    PACKAGE_ANDROID = "com.ss.android.ugc.aweme"
    ACTIVITY_ANDROID = "com.ss.android.ugc.aweme.splash.SplashActivity"

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
        logger.debug(f"[Douyin/{('Android' if self.is_android else 'iOS')}] 搜索: {keyword}")
        if self.is_android:
            return self._search_android(keyword)
        return self._search_ios(keyword)

    def _search_android(self, keyword: str) -> bool:
        drv = self.driver
        # 点击搜索图标（抖音顶栏右侧放大镜）
        for by, val in [
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().description("搜索")'),
            (AppiumBy.XPATH, '//*[@content-desc="搜索"]'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().resourceIdMatches(".*search.*icon.*")'),
        ]:
            el = drv.try_find(by, val)
            if el:
                el.click()
                break
        else:
            logger.warning("[Douyin] Android: 未找到搜索入口")
            return False

        time.sleep(1.0)

        field = drv.try_find(AppiumBy.CLASS_NAME, "android.widget.EditText")
        if not field:
            logger.warning("[Douyin] Android: 未找到输入框")
            return False

        field.clear()
        field.send_keys(keyword)
        time.sleep(0.5)

        from drivers.android_driver import AndroidDriver
        assert isinstance(drv, AndroidDriver)
        drv.press_search_key()
        time.sleep(self.result_wait)

        # 切换到视频 tab
        for tab in ["视频", "综合"]:
            el = drv.try_find(AppiumBy.ANDROID_UIAUTOMATOR,
                              f'new UiSelector().text("{tab}")')
            if el:
                el.click()
                time.sleep(1.5)
                break

        return True

    def _search_ios(self, keyword: str) -> bool:
        drv = self.driver
        for by, val in [
            ("accessibility id", "搜索"),
            ("xpath", '//XCUIElementTypeButton[contains(@name,"搜索")]'),
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

        for tab in ["视频", "综合"]:
            el = drv.try_find("accessibility id", tab)
            if el:
                el.click()
                time.sleep(1.5)
                break
        return True

    # ──────────────────────────── collection ─────────────────────────────

    def collect_items(self, keyword: str, max_count: int) -> list[ContentItem]:
        items: list[ContentItem] = []
        seen: set[str] = set()
        scrolls = 0

        while len(items) < max_count and scrolls < 25:
            cells = self._find_cells()
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
            for by, val in [
                (AppiumBy.XPATH, '//androidx.recyclerview.widget.RecyclerView/android.view.ViewGroup'),
                (AppiumBy.XPATH, '//android.view.ViewGroup[@clickable="true"]'),
            ]:
                cells = self.driver.driver.find_elements(by, val)
                if cells:
                    return cells
        else:
            cells = self.driver.driver.find_elements(AppiumBy.CLASS_NAME, "XCUIElementTypeCell")
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
            platform="抖音",
            keyword=keyword,
            title=title,
            author=author,
            likes=stats["likes"],
            comments=stats["comments"],
            shares=stats["shares"],
            content_type="video",
            tags=self.extractor.extract_tags(" ".join(texts)),
            screenshot_path=ss_path,
        )
        item.compute_engagement()
        return item
