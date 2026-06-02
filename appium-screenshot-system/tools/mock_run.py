"""
Mock 运行：不连接真机，生成假数据测试 Excel 输出、情感分析、报告生成。
用法:
  python tools/mock_run.py
"""
from __future__ import annotations

import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.content_item import ContentItem, SearchSession
from analysis.sentiment import SentimentAnalyzer
from analysis.ranking import RankingAnalyzer
from output.excel_writer import ExcelWriter
from output.report_generator import ReportGenerator
from utils.logger import setup_logger, log_ok

TITLES = [
    "2024年最值得入手的护肤品，我测了一整年！",
    "平价好用的10款护肤好物推荐，学生党必看",
    "踩雷预警！这些护肤品千万别买",
    "敏感肌救星，温和不刺激的护肤品大合集",
    "护肤干货：正确护肤步骤，少走弯路",
    "博主亲测！护肤品成分解析，别被营销忽悠了",
    "冬季护肤攻略，补水保湿这样做才对",
    "美白护肤品测评，哪款真的有效？",
    "护肤品使用顺序大盘点，你用对了吗",
    "学生党护肤预算100元怎么用？超全攻略",
]
AUTHORS = ["美妆博主小A", "护肤达人", "皮肤科医生推荐", "素人测评", "美妆编辑部", "种草机器人"]


def make_mock_items(keyword: str, platform: str, n: int = 30) -> list[ContentItem]:
    items = []
    for i in range(1, n + 1):
        title = random.choice(TITLES) + f" #{i}"
        likes = random.randint(100, 500000)
        comments = random.randint(10, int(likes * 0.1))
        shares = random.randint(0, int(likes * 0.05))
        collects = random.randint(0, int(likes * 0.2))
        views = random.randint(likes, likes * 20)
        item = ContentItem(
            rank=i,
            platform=platform,
            keyword=keyword,
            title=title,
            author=random.choice(AUTHORS),
            likes=likes,
            comments=comments,
            shares=shares,
            collects=collects,
            views=views,
            content_type=random.choice(["video", "image", "article"]),
            tags=random.sample(["护肤", "美妆", "好物推荐", "种草", "干货"], k=random.randint(1, 3)),
        )
        item.compute_engagement()
        items.append(item)
    return items


def main():
    setup_logger(level="DEBUG")
    print("=== Mock 运行（无需真机）===\n")

    keyword = "护肤品推荐"
    platform = "小红书"

    items = make_mock_items(keyword, platform, n=30)

    # 情感分析
    analyzer = SentimentAnalyzer()
    analyzer.analyze_batch(items)

    session = SearchSession(platform=platform, keyword=keyword)
    session.items = items
    session.total_captured = len(items)
    session.end_time = datetime.now()

    # 排名分析
    analysis = RankingAnalyzer().analyze(items)

    # Excel 输出
    writer = ExcelWriter(output_dir="output/mock_data")
    excel_path = writer.write_session(session, analysis)
    log_ok(f"Excel: {excel_path}")

    # HTML 报告
    reporter = ReportGenerator(output_dir="output/mock_reports")
    html_path = reporter.generate(session, analysis)
    log_ok(f"HTML 报告: {html_path}")

    # 打印摘要
    print(f"\n关键词: {keyword}   平台: {platform}")
    print(f"正面内容: {analysis['positive_ratio']}%   负面: {analysis['negative_ratio']}%")
    print(f"竞争等级: {analysis['competition_level']}   平均点赞: {analysis['avg_likes']:,}")
    hot = ", ".join(f"{w}({c})" for w, c in analysis.get("hot_words", [])[:5])
    print(f"热词: {hot}")


if __name__ == "__main__":
    main()
