from __future__ import annotations

import pytest
from models.content_item import ContentItem
from analysis.ranking import RankingAnalyzer


def make_item(rank, likes=100, sentiment="positive"):
    item = ContentItem(rank=rank, platform="小红书", keyword="测试",
                        title=f"标题{rank}", likes=likes, views=10000)
    item.sentiment_label = sentiment
    item.compute_engagement()
    return item


def test_basic_analysis():
    items = [make_item(i, likes=i * 100) for i in range(1, 21)]
    result = RankingAnalyzer().analyze(items)
    assert result["total_items"] == 20
    assert result["avg_likes"] > 0
    assert "competition_level" in result


def test_empty():
    result = RankingAnalyzer().analyze([])
    assert result == {}


def test_sentiment_ratio():
    items = [make_item(i, sentiment="positive") for i in range(1, 6)]
    items += [make_item(i + 5, sentiment="negative") for i in range(1, 4)]
    result = RankingAnalyzer().analyze(items)
    assert result["positive_ratio"] > 0
    assert result["negative_ratio"] > 0
