from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from models.content_item import ContentItem, SearchSession
from screenshot.capture import ScreenshotCapture
from parser.data_extractor import DataExtractor
from utils.helpers import safe_filename, ensure_dir

if TYPE_CHECKING:
    from drivers.base_driver import BaseDriver
    from config.loader import ConfigLoader
    from parser.ocr_engine import OCREngine


class BaseApp(ABC):
    """所有 App 自动化的基类"""

    platform_name: str = ""
    app_name: str = ""

    def __init__(self, driver: "BaseDriver", config: "ConfigLoader",
                 ocr: "OCREngine | None" = None):
        self.driver = driver
        self.config = config
        self.ocr = ocr
        app_cfg = config.app_config(self.app_name)
        ss_cfg = config.screenshot_cfg()

        self.max_results: int = app_cfg.get("max_results", 30)
        self.search_wait: float = app_cfg.get("search_wait", 3.0)
        self.result_wait: float = app_cfg.get("result_wait", 2.5)
        self.scroll_pause: float = app_cfg.get("scroll_pause", 1.5)
        self.locators: dict = app_cfg.get("locators", {}).get(
            "ios" if self.platform_name == "iOS" else "windows", {}
        )

        ss_out = ss_cfg.get("output_dir", "output/screenshots")
        self.capture = ScreenshotCapture(
            driver=driver,
            output_dir=ss_out,
            scroll_distance=ss_cfg.get("scroll_distance", 800),
            scroll_pause=ss_cfg.get("scroll_pause", 1.5),
            status_bar_height=ss_cfg.get("status_bar_height", 44),
            max_scrolls=ss_cfg.get("scroll_count", 15),
        )
        self.extractor = DataExtractor(driver, ocr)

    # ──────────────────────────── lifecycle ──────────────────────────────

    @abstractmethod
    def open(self) -> None:
        """启动并打开 App 到首页"""
        ...

    @abstractmethod
    def search(self, keyword: str) -> bool:
        """执行搜索，返回是否成功进入结果页"""
        ...

    @abstractmethod
    def collect_items(self, keyword: str, max_count: int) -> list[ContentItem]:
        """滚动采集 TOP N 条内容数据"""
        ...

    # ──────────────────────────── main workflow ──────────────────────────

    def run_keyword(self, keyword: str, top_n: int | None = None) -> SearchSession:
        n = top_n or self.max_results
        session = SearchSession(platform=self.app_name, keyword=keyword)
        logger.info(f"[{self.app_name}] 开始搜索关键词: 「{keyword}」，目标 TOP {n}")

        try:
            self.open()
            ok = self.search(keyword)
            if not ok:
                session.error = "搜索失败，未进入结果页"
                return session

            # 结果页长截图
            fname = safe_filename(f"{self.app_name}_{keyword}_overview.png")
            long_ss_path = self.capture.take_long(
                f"{self.app_name}/{safe_filename(keyword)}/{fname}"
            )

            # 滚动采集数据
            items = self.collect_items(keyword, n)

            # 补充长截图路径到所有 item
            for item in items:
                item.long_screenshot_path = str(long_ss_path)

            session.items = items
            session.total_captured = len(items)
            logger.info(f"[{self.app_name}] 关键词「{keyword}」采集完成，共 {len(items)} 条")

        except Exception as exc:
            session.error = str(exc)
            logger.error(f"[{self.app_name}] 关键词「{keyword}」采集失败: {exc}")

        from datetime import datetime
        session.end_time = datetime.now()
        return session

    # ──────────────────────────── helpers ────────────────────────────────

    def _loc(self, key: str) -> tuple[str, str]:
        """从 locator 配置取 (by, value)"""
        loc = self.locators.get(key, {})
        return loc.get("by", "accessibility id"), loc.get("value", key)

    def _try_tap(self, key: str) -> bool:
        by, value = self._loc(key)
        el = self.driver.try_find(by, value)
        if el:
            el.click()
            return True
        return False

    def _scroll_to_load_more(self, current_count: int, target: int) -> bool:
        """滚动以加载更多内容，返回 False 表示已到底"""
        before = current_count
        self.driver.scroll_down()
        time.sleep(self.scroll_pause)
        return True  # 子类可重写以检测页面底部

    def _item_screenshot(self, element, keyword: str, rank: int) -> str:
        """单个 item 截图"""
        try:
            fname = safe_filename(f"{keyword}_rank{rank:02d}.png")
            path = ensure_dir(
                self.capture.output_dir / self.app_name / safe_filename(keyword)
            ) / fname
            png = element.screenshot_as_png
            with open(path, "wb") as f:
                f.write(png)
            return str(path)
        except Exception as exc:
            logger.debug(f"单项截图失败: {exc}")
            return ""
