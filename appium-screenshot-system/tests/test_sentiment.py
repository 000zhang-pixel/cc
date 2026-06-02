from __future__ import annotations

import pytest
from analysis.sentiment import SentimentAnalyzer


@pytest.fixture
def sa():
    return SentimentAnalyzer()


def test_positive_keyword(sa):
    score = sa.score("这款护肤品真的好用，强烈推荐！")
    assert score > 0.5

def test_negative_keyword(sa):
    score = sa.score("踩雷了，差评，千万别买")
    assert score < 0.5

def test_label_positive(sa):
    assert sa.label(0.8) == "positive"

def test_label_negative(sa):
    assert sa.label(0.2) == "negative"

def test_label_neutral(sa):
    assert sa.label(0.5) == "neutral"

def test_neutral_text(sa):
    score = sa.score("这是一条普通的内容介绍")
    assert 0.0 <= score <= 1.0
