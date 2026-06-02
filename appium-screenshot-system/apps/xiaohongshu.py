from __future__ import annotations

import time
from loguru import logger
from appium.webdriver.common.appiumby import AppiumBy

from apps.base_app import BaseApp
from models.content_item import ContentItem
from utils.helpers import parse_count, safe_filename


class XiaohongshuApp(BaseApp):
    """小红书 iOS 自动化"""

    platform_name = "iOS"
    app_name = "xiaohongshu"
    BUNDLE_ID = "com.xingin.discover"

    # ──────────────────────────── lifecycle ──────────────────────────────

    def open(self) -> None:
        from drivers.ios_driver import IOSDriver
        assert isinstance(self.driver, IOSDriver)
        self.driver.launch_app(self.BUNDLE_ID)
        self.driver.dismiss_alert()
        time.sleep(self.search_wait)

    # ──────────────────────────── search ─────────────────────────────────

    def search(self, keyword: str) -> bool:
        driver = self.driver
        logger.debug(f"[XHS] 搜索: {keyword}")

        # 点击首页搜索入口（多种定位策略容错）
        search_tapped = False
        for by, val in [
            ("accessibility id", "搜索"),
            ("xpath", '//XCUIElementTypeButton[@name="搜索"]'),
            ("xpath", '//XCUIElementTypeSearchField'),
        ]:
            el = driver.try_find(by, val)
            if el:
                el.click()
                search_tapped = True
                break

        if not search_tapped:
            logger.warning("[XHS] 未找到搜索入口")
            return False

        time.sleep(1.0)

        # 输入关键词
        field = None
        for by, val in [
            ("class name", "XCUIElementTypeTextField"),
            ("class name", "XCUIElementTypeSearchField"),
            ("xpath", '//XCUIElementTypeTextField'),
        ]:
            field = driver.try_find(by, val)
            if field:
                break

        if not field:
            logger.warning("[XHS] 未找到搜索输入框")
            return False

        field.clear()
        field.send_keys(keyword)
        time.sleep(0.8)

        # 确认搜索（键盘搜索按钮）
        driver.hide_keyboard()
        time.sleep(0.5)

        # 有些版本有独立的"搜索"确认按钮
        confirm = driver.try_find("xpath",
            f'//XCUIElementTypeButton[@name="搜索" or @name="Search"]')
        if confirm:
            confirm.click()

        time.sleep(self.result_wait)
        return True

    # ──────────────────────────── data collection ─────────────────────────

    def collect_items(self, keyword: str, max_count: int) -> list[ContentItem]:
        items: list[ContentItem] = []
        seen_titles: set[str] = set()
        scroll_attempts = 0
        max_scrolls = 20

        logger.info(f"[XHS] 开始采集，目标 {max_count} 条")

        while len(items) < max_count and scroll_attempts < max_scrolls:
            cells = self._find_result_cells()
            logger.debug(f"[XHS] 当前屏幕 {len(cells)} 个 cell，已采集 {len(items)} 条")

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

        logger.info(f"[XHS] 采集完毕，共 {len(items)} 条")
        return items

    # ──────────────────────────── cell parsing ────────────────────────────

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
        if not texts:
            return None

        title = texts[0] if texts else ""
        if not title or title in seen:
            return None

        author = texts[1] if len(texts) > 1 else ""

        # 解析互动数据
        stats = self.extractor.parse_stats_from_texts(texts[2:] if len(texts) > 2 else [])

        # 单 item 截图
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
            content_type=self._detect_type(texts),
            tags=self.extractor.extract_tags(" ".join(texts)),
            screenshot_path=ss_path,
        )
        item.compute_engagement()
        return item

    def _detect_type(self, texts: list[str]) -> str:
        joined = " ".join(texts).lower()
        if any(k in joined for k in ["视频", "video", "▶"]):
            return "video"
        if any(k in joined for k in ["图文", "图片"]):
            return "image"
        return "image"
