from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ContentItem:
    rank: int
    platform: str
    keyword: str
    title: str = ""
    author: str = ""
    author_id: str = ""
    author_followers: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    collects: int = 0
    views: int = 0
    content_type: str = ""          # video / image / article / mix
    tags: list[str] = field(default_factory=list)
    url: str = ""
    screenshot_path: str = ""
    long_screenshot_path: str = ""
    ocr_text: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    sentiment_score: float = 0.5    # 0=负面 1=正面
    sentiment_label: str = "neutral"  # positive / negative / neutral
    engagement_rate: float = 0.0

    # 舆情分析字段
    hot_words: list[str] = field(default_factory=list)
    risk_level: str = "low"         # low / medium / high
    topic_category: str = ""

    def compute_engagement(self) -> None:
        total = self.likes + self.comments + self.shares + self.collects
        denom = max(self.views, 1)
        self.engagement_rate = round(total / denom * 100, 2)

    def to_dict(self) -> dict:
        return {
            "排名": self.rank,
            "平台": self.platform,
            "关键词": self.keyword,
            "内容标题": self.title,
            "作者": self.author,
            "作者粉丝数": self.author_followers,
            "点赞数": self.likes,
            "评论数": self.comments,
            "分享数": self.shares,
            "收藏数": self.collects,
            "播放量": self.views,
            "互动率%": self.engagement_rate,
            "内容类型": self.content_type,
            "标签": "、".join(self.tags),
            "链接": self.url,
            "情感得分": self.sentiment_score,
            "情感倾向": self.sentiment_label,
            "热词": "、".join(self.hot_words),
            "风险等级": self.risk_level,
            "话题分类": self.topic_category,
            "截图路径": self.screenshot_path,
            "长截图路径": self.long_screenshot_path,
            "采集时间": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        }


@dataclass
class SearchSession:
    """一次搜索任务的元数据"""
    platform: str
    keyword: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    total_captured: int = 0
    items: list[ContentItem] = field(default_factory=list)
    error: Optional[str] = None

    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def success(self) -> bool:
        return self.error is None and len(self.items) > 0
