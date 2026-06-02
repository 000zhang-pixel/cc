from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.content_item import ContentItem


class RankingAnalyzer:
    """搜索排名与占位分析"""

    def analyze(self, items: list["ContentItem"]) -> dict:
        if not items:
            return {}

        keyword = items[0].keyword
        platform = items[0].platform

        # 基础统计
        total = len(items)
        likes = [i.likes for i in items]
        comments = [i.comments for i in items]
        shares = [i.shares for i in items]

        # 作者分布
        author_counter = Counter(i.author for i in items if i.author)
        top_authors = author_counter.most_common(5)

        # 内容类型分布
        type_counter = Counter(i.content_type for i in items if i.content_type)

        # 情感分布
        sentiment_dist = Counter(i.sentiment_label for i in items)

        # 风险分布
        risk_dist = Counter(i.risk_level for i in items)

        # TOP5 热词
        all_words: list[str] = []
        for item in items:
            all_words.extend(item.hot_words)
        hot_word_counter = Counter(all_words).most_common(10)

        # 标签 TOP10
        all_tags: list[str] = []
        for item in items:
            all_tags.extend(item.tags)
        top_tags = Counter(all_tags).most_common(10)

        # 互动率分层（TOP1-5 / TOP6-15 / TOP16-30）
        tier_engagement = self._tier_engagement(items)

        # 竞争强度：TOP10 总点赞均值
        top10_likes = [i.likes for i in sorted(items, key=lambda x: x.rank)[:10]]
        competition_score = sum(top10_likes) / len(top10_likes) if top10_likes else 0

        return {
            "keyword": keyword,
            "platform": platform,
            "total_items": total,
            "avg_likes": round(sum(likes) / max(total, 1)),
            "avg_comments": round(sum(comments) / max(total, 1)),
            "avg_shares": round(sum(shares) / max(total, 1)),
            "max_likes": max(likes, default=0),
            "min_likes": min(likes, default=0),
            "top_authors": top_authors,
            "author_diversity": len(author_counter),          # 去重作者数
            "content_type_dist": dict(type_counter),
            "sentiment_dist": dict(sentiment_dist),
            "positive_ratio": round(sentiment_dist.get("positive", 0) / max(total, 1) * 100, 1),
            "negative_ratio": round(sentiment_dist.get("negative", 0) / max(total, 1) * 100, 1),
            "risk_dist": dict(risk_dist),
            "high_risk_count": risk_dist.get("high", 0),
            "hot_words": hot_word_counter,
            "top_tags": top_tags,
            "tier_engagement": tier_engagement,
            "competition_score": round(competition_score),
            "competition_level": self._competition_level(competition_score),
        }

    def _tier_engagement(self, items: list["ContentItem"]) -> dict:
        sorted_items = sorted(items, key=lambda x: x.rank)
        tiers = {"TOP1-5": [], "TOP6-15": [], "TOP16+": []}
        for item in sorted_items:
            if item.rank <= 5:
                tiers["TOP1-5"].append(item.engagement_rate)
            elif item.rank <= 15:
                tiers["TOP6-15"].append(item.engagement_rate)
            else:
                tiers["TOP16+"].append(item.engagement_rate)

        result = {}
        for k, v in tiers.items():
            result[k] = round(sum(v) / len(v), 2) if v else 0.0
        return result

    @staticmethod
    def _competition_level(score: float) -> str:
        if score >= 100000:
            return "极高"
        if score >= 10000:
            return "高"
        if score >= 1000:
            return "中"
        return "低"

    def summary_table(self, analysis: dict) -> list[dict]:
        """将分析结果转为表格行（用于写入 Excel 汇总 sheet）"""
        rows = []
        for field, label in [
            ("keyword", "关键词"),
            ("platform", "平台"),
            ("total_items", "采集条数"),
            ("avg_likes", "平均点赞"),
            ("avg_comments", "平均评论"),
            ("avg_shares", "平均分享"),
            ("max_likes", "最高点赞"),
            ("author_diversity", "去重作者数"),
            ("positive_ratio", "正面内容占比%"),
            ("negative_ratio", "负面内容占比%"),
            ("high_risk_count", "高风险条数"),
            ("competition_score", "竞争强度分"),
            ("competition_level", "竞争等级"),
        ]:
            rows.append({"指标": label, "值": analysis.get(field, "")})

        rows.append({"指标": "TOP1-5 互动率%", "值": analysis.get("tier_engagement", {}).get("TOP1-5", 0)})
        rows.append({"指标": "TOP6-15 互动率%", "值": analysis.get("tier_engagement", {}).get("TOP6-15", 0)})

        top5_authors = "; ".join(f"{a}({c}条)" for a, c in analysis.get("top_authors", [])[:5])
        rows.append({"指标": "TOP5 作者", "值": top5_authors})

        hot = "; ".join(f"{w}({c})" for w, c in analysis.get("hot_words", [])[:5])
        rows.append({"指标": "热词TOP5", "值": hot})

        return rows
