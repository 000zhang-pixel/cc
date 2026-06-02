from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

try:
    from snownlp import SnowNLP
    _SNOW_OK = True
except ImportError:
    _SNOW_OK = False
    logger.warning("snownlp 未安装，情感分析将使用关键词规则。运行: pip install snownlp")

if TYPE_CHECKING:
    from models.content_item import ContentItem


class SentimentAnalyzer:

    def __init__(self, pos_threshold: float = 0.6, neg_threshold: float = 0.4,
                 positive_kws: list[str] | None = None,
                 negative_kws: list[str] | None = None):
        self.pos_threshold = pos_threshold
        self.neg_threshold = neg_threshold
        self.positive_kws = set(positive_kws or [
            "好用", "推荐", "优质", "种草", "爱了", "绝绝子", "超好",
            "值得买", "yyds", "完美", "好评", "入手", "必买",
        ])
        self.negative_kws = set(negative_kws or [
            "踩雷", "差评", "不推荐", "退货", "坑", "难用", "失望",
            "翻车", "后悔", "避雷", "垃圾",
        ])

    # ──────────────────────────── core ──────────────────────────────────

    def score(self, text: str) -> float:
        """返回 0~1 的情感得分，1 = 极正面，0 = 极负面"""
        if not text or not text.strip():
            return 0.5

        # 关键词规则层
        kw_bias = self._keyword_bias(text)

        if _SNOW_OK:
            try:
                snow_score = SnowNLP(text).sentiments
                # 混合：60% SnowNLP + 40% 关键词规则
                combined = snow_score * 0.6 + (0.5 + kw_bias * 0.5) * 0.4
                return round(max(0.0, min(1.0, combined)), 4)
            except Exception:
                pass

        # 纯关键词规则
        return round(max(0.0, min(1.0, 0.5 + kw_bias * 0.5)), 4)

    def label(self, score: float) -> str:
        if score >= self.pos_threshold:
            return "positive"
        if score <= self.neg_threshold:
            return "negative"
        return "neutral"

    def analyze(self, item: "ContentItem") -> None:
        text = f"{item.title} {' '.join(item.tags)} {item.ocr_text}"
        s = self.score(text)
        item.sentiment_score = s
        item.sentiment_label = self.label(s)
        item.hot_words = self._extract_hot_words(text)
        item.risk_level = self._risk_level(text, s)

    def analyze_batch(self, items: list["ContentItem"]) -> None:
        for item in items:
            self.analyze(item)

    # ──────────────────────────── helpers ────────────────────────────────

    def _keyword_bias(self, text: str) -> float:
        """返回 -1~1，正数偏正面"""
        pos = sum(1 for kw in self.positive_kws if kw in text)
        neg = sum(1 for kw in self.negative_kws if kw in text)
        denom = max(pos + neg, 1)
        return (pos - neg) / denom

    def _extract_hot_words(self, text: str) -> list[str]:
        found = []
        for kw in self.positive_kws | self.negative_kws:
            if kw in text:
                found.append(kw)
        # 话题标签
        tags = re.findall(r"#([^\s#@]{2,10})", text)
        return list(dict.fromkeys(found + tags))[:10]

    @staticmethod
    def _risk_level(text: str, score: float) -> str:
        high_risk_words = ["违规", "虚假", "诈骗", "假冒", "投诉", "315", "曝光", "黑幕"]
        if any(w in text for w in high_risk_words):
            return "high"
        if score <= 0.3:
            return "medium"
        return "low"
