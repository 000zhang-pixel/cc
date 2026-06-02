from __future__ import annotations

import time
from loguru import logger
from appium.webdriver.common.appiumby import AppiumBy

from apps.base_app import BaseApp
from models.content_item import ContentItem
from utils.helpers import parse_count


class DouyinApp(BaseApp):
    """抖音 iOS 自动化"""

    platform_name = "iOS"
    app_name = "douyin"
    BUNDLE_ID = "com.ss.iphone.ugc.Aweme"

    def open(self) -> None:
        from drivers.ios_driver import IOSDriver
        assert isinstance(self.driver, IOSDriver)
        self.driver.launch_app(self.BUNDLE_ID)
        self.driver.dismiss_alert()
        time.sleep(self.search_wait)

    # ──────────────────────────── search ─────────────────────────────────

    def search(self, keyword: str) -> bool:
        driver = self.driver
        logger.debug(f"[Douyin] 搜索: {keyword}")

        # 点击搜索图标
        for by, val in [
            ("accessibility id", "搜索"),
            ("xpath", '//XCUIElementTypeButton[contains(@name,"搜索")]'),
            ("xpath", '//XCUIElementTypeImage[@name="icon_homepage_search"]'),
        ]:
            el = driver.try_find(by, val)
            if el:
                el.click()
                break
        else:
            logger.warning("[Douyin] 未找到搜索入口")
            return False

        time.sleep(1.0)

        # 输入关键词
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
            logger.warning("[Douyin] 未找到搜索框")
            return False

        time.sleep(0.5)
        driver.hide_keyboard()
        time.sleep(0.3)

        # 点击搜索确认
        for by, val in [
            ("accessibility id", "搜索"),
            ("xpath", '//XCUIElementTypeButton[@name="搜索"]'),
        ]:
            btn = driver.try_find(by, val)
            if btn:
                btn.click()
                break

        time.sleep(self.result_wait)

        # 切换到"视频"tab（有些版本默认显示综合）
        for tab_name in ["视频", "综合", "作品"]:
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
        max_scrolls = 25

        while len(items) < max_count and scroll_attempts < max_scrolls:
            cells = self._find_result_cells()
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

    def _find_result_cells(self) -> list:
        for by, val in [
            (AppiumBy.CLASS_NAME, "XCUIElementTypeCell"),
            (AppiumBy.XPATH, '//XCUIElementTypeCell'),
        ]:
            cells = self.driver.driver.find_elements(by, val)
            if cells:
                return cells
        return []

    def _parse_cell(self, cell, keyword: str, rank: int,
                    seen: set[str]) -> ContentItem | None:
        texts = self.extractor.texts_from_children(cell)
        if not texts or len(texts) < 1:
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
