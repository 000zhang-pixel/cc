from __future__ import annotations

import time
from loguru import logger
from appium.webdriver.common.appiumby import AppiumBy

from apps.base_app import BaseApp
from models.content_item import ContentItem


class WechatApp(BaseApp):
    """微信 iOS 搜索（公众号文章 / 视频号）"""

    platform_name = "iOS"
    app_name = "wechat"
    BUNDLE_ID = "com.tencent.xin"

    def open(self) -> None:
        from drivers.ios_driver import IOSDriver
        assert isinstance(self.driver, IOSDriver)
        self.driver.launch_app(self.BUNDLE_ID)
        self.driver.dismiss_alert()
        time.sleep(self.search_wait)

    # ──────────────────────────── search ─────────────────────────────────

    def search(self, keyword: str) -> bool:
        driver = self.driver
        logger.debug(f"[WeChat] 搜索: {keyword}")

        for by, val in [
            ("xpath", '//XCUIElementTypeNavigationBar//XCUIElementTypeButton'),
            ("accessibility id", "搜索"),
            ("xpath", '//XCUIElementTypeSearchField'),
        ]:
            el = driver.try_find(by, val)
            if el:
                el.click()
                break
        else:
            logger.warning("[WeChat] 未找到搜索入口")
            return False

        time.sleep(1.0)

        for by, val in [
            ("class name", "XCUIElementTypeTextField"),
            ("class name", "XCUIElementTypeSearchField"),
            ("xpath", '//XCUIElementTypeTextField'),
        ]:
            field = driver.try_find(by, val)
            if field:
                field.clear()
                field.send_keys(keyword)
                break
        else:
            return False

        time.sleep(0.5)
        driver.hide_keyboard()

        for by, val in [
            ("accessibility id", "搜索"),
            ("xpath", '//XCUIElementTypeButton[@name="搜索" or @name="Search"]'),
        ]:
            btn = driver.try_find(by, val)
            if btn:
                btn.click()
                break

        time.sleep(self.result_wait)

        # 切换到公众号文章 tab
        for tab_name in ["公众号", "文章"]:
            tab = driver.try_find("accessibility id", tab_name)
            if tab:
                tab.click()
                time.sleep(1.5)
                break

        return True

    # ──────────────────────────── collection ─────────────────────────────

    def collect_items(self, keyword: str, max_count: int) -> list[ContentItem]:
        items: list[ContentItem] = []
        seen_titles: set[str] = set()
        scroll_attempts = 0

        while len(items) < max_count and scroll_attempts < 20:
            cells = self.driver.driver.find_elements(AppiumBy.CLASS_NAME, "XCUIElementTypeCell")
            for cell in cells:
                if len(items) >= max_count:
                    break
                item = self._parse_cell(cell, keyword, rank=len(items) + 1, seen=seen_titles)
                if item:
                    items.append(item)
                    seen_titles.add(item.title)

            if len(items) >= max_count:
                break
            self.driver.scroll_down()
            time.sleep(self.scroll_pause)
            scroll_attempts += 1

        return items

    def _parse_cell(self, cell, keyword: str, rank: int,
                    seen: set[str]) -> ContentItem | None:
        texts = self.extractor.texts_from_children(cell)
        if not texts:
            return None
        title = texts[0]
        if not title or title in seen:
            return None

        author = texts[1] if len(texts) > 1 else ""
        ss_path = self._item_screenshot(cell, keyword, rank)

        return ContentItem(
            rank=rank,
            platform="微信",
            keyword=keyword,
            title=title,
            author=author,
            content_type="article",
            tags=self.extractor.extract_tags(" ".join(texts)),
            screenshot_path=ss_path,
        )
