from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

from loguru import logger
from utils.helpers import parse_count

if TYPE_CHECKING:
    from drivers.base_driver import BaseDriver
    from parser.ocr_engine import OCREngine


class DataExtractor:
    """
    从 Appium 元素属性中提取结构化数据，
    当元素属性为空时回退到 OCR。
    """

    def __init__(self, driver: "BaseDriver", ocr: Optional["OCREngine"] = None):
        self.driver = driver
        self.ocr = ocr

    # ──────────────────────────── generic ───────────────────────────────

    def element_text(self, element) -> str:
        for attr in ("text", "label", "value", "name", "content-desc"):
            try:
                v = element.get_attribute(attr)
                if v and v.strip():
                    return v.strip()
            except Exception:
                pass
        return ""

    def texts_from_children(self, element, by: str = "class name",
                             value: str = "XCUIElementTypeStaticText") -> list[str]:
        from appium.webdriver.common.appiumby import AppiumBy
        mapping = {
            "class name": AppiumBy.CLASS_NAME,
            "xpath": AppiumBy.XPATH,
            "accessibility id": AppiumBy.ACCESSIBILITY_ID,
        }
        try:
            els = element.find_elements(mapping.get(by, by), value)
            return [self.element_text(e) for e in els if self.element_text(e)]
        except Exception:
            return []

    # ──────────────────────────── number parsing ─────────────────────────

    @staticmethod
    def parse_count(text: str) -> int:
        return parse_count(text)

    def extract_count(self, element) -> int:
        return parse_count(self.element_text(element))

    # ──────────────────────────── OCR fallback ──────────────────────────

    def ocr_element(self, element) -> str:
        if self.ocr is None:
            return ""
        try:
            png = element.screenshot_as_png
            return self.ocr.read_text(png)
        except Exception as exc:
            logger.debug(f"OCR 回退失败: {exc}")
            return ""

    # ──────────────────────────── structured field parsers ───────────────

    def parse_stats_from_texts(self, texts: list[str]) -> dict:
        """
        从一批文本中提取点赞/评论/分享/收藏/播放数
        """
        result = {"likes": 0, "comments": 0, "shares": 0, "collects": 0, "views": 0}
        patterns = {
            "views": re.compile(r"^[\d.]+[万亿kKwW]?$"),
            "likes": re.compile(r"(赞|like|❤|👍|♥)"),
            "comments": re.compile(r"(评论|comment|💬)"),
            "shares": re.compile(r"(分享|share|转发)"),
            "collects": re.compile(r"(收藏|collect|⭐|🌟|favorit)"),
        }
        # 数字类文本列表
        num_texts = []
        for t in texts:
            is_num = bool(re.match(r"^[\d.,万亿kKwW]+$", t.strip()))
            if is_num:
                num_texts.append(t)

        # 用位置启发式匹配：通常顺序为 点赞-评论-分享-收藏
        if len(num_texts) >= 4:
            keys = ["likes", "comments", "shares", "collects"]
            for k, v in zip(keys, num_texts):
                result[k] = parse_count(v)
        elif len(num_texts) == 3:
            for k, v in zip(["likes", "comments", "shares"], num_texts):
                result[k] = parse_count(v)
        elif len(num_texts) >= 1:
            result["likes"] = parse_count(num_texts[0])

        return result

    def extract_tags(self, text: str) -> list[str]:
        """从文本中提取 #话题标签"""
        return re.findall(r"#([^\s#@]+)", text)
