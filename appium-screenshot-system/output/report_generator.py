from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from utils.helpers import ensure_dir, safe_filename

if TYPE_CHECKING:
    from models.content_item import ContentItem, SearchSession


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>舆情分析报告 - {keyword} @ {platform}</title>
<style>
  body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif; margin: 0; background: #f5f5f5; color: #333; }}
  .header {{ background: linear-gradient(135deg, #2d6a4f, #52b788); color: #fff; padding: 30px 40px; }}
  .header h1 {{ margin: 0; font-size: 28px; }}
  .header p {{ margin: 6px 0 0; opacity: .85; }}
  .container {{ max-width: 1200px; margin: 30px auto; padding: 0 20px; }}
  .card {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,.08); padding: 24px; margin-bottom: 24px; }}
  .card h2 {{ margin-top: 0; font-size: 18px; border-left: 4px solid #52b788; padding-left: 12px; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
  .stat {{ text-align: center; padding: 20px; background: #f0faf4; border-radius: 10px; }}
  .stat .val {{ font-size: 32px; font-weight: 700; color: #2d6a4f; }}
  .stat .lbl {{ font-size: 13px; color: #666; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #2d6a4f; color: #fff; padding: 10px 12px; text-align: left; }}
  td {{ padding: 9px 12px; border-bottom: 1px solid #eee; }}
  tr:nth-child(even) td {{ background: #f9f9f9; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
  .pos {{ background: #d8f3dc; color: #1b4332; }}
  .neg {{ background: #ffccd5; color: #7d0000; }}
  .neutral {{ background: #e9ecef; color: #495057; }}
  .risk-high {{ background: #ff4d4d; color: #fff; }}
  .risk-medium {{ background: #ffa500; color: #fff; }}
  .risk-low {{ background: #52b788; color: #fff; }}
  .bar-wrap {{ display: flex; align-items: center; gap: 10px; }}
  .bar {{ height: 12px; border-radius: 6px; background: #52b788; }}
</style>
</head>
<body>
<div class="header">
  <h1>📊 搜索舆情分析报告</h1>
  <p>平台：{platform} &nbsp;|&nbsp; 关键词：{keyword} &nbsp;|&nbsp; 生成时间：{gen_time}</p>
</div>
<div class="container">

  <!-- 核心指标 -->
  <div class="card">
    <h2>核心指标</h2>
    <div class="stats-grid">
      <div class="stat"><div class="val">{total}</div><div class="lbl">采集条数</div></div>
      <div class="stat"><div class="val">{avg_likes}</div><div class="lbl">平均点赞</div></div>
      <div class="stat"><div class="val">{positive_ratio}%</div><div class="lbl">正面内容占比</div></div>
      <div class="stat"><div class="val">{competition_level}</div><div class="lbl">竞争等级</div></div>
    </div>
  </div>

  <!-- 热词 -->
  <div class="card">
    <h2>热词 TOP10</h2>
    {hot_words_html}
  </div>

  <!-- TOP 内容列表 -->
  <div class="card">
    <h2>TOP 内容列表</h2>
    <table>
      <thead><tr><th>#</th><th>标题</th><th>作者</th><th>点赞</th><th>评论</th><th>情感</th><th>风险</th></tr></thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

</div>
</body>
</html>"""


class ReportGenerator:

    def __init__(self, output_dir: str = "output/reports"):
        self.output_dir = ensure_dir(output_dir)

    def generate(self, session: "SearchSession", analysis: dict) -> Path:
        keyword = session.keyword
        platform = session.platform
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{safe_filename(platform)}_{safe_filename(keyword)}_{ts}.html"
        path = self.output_dir / fname

        hot_words_html = self._hot_words_html(analysis.get("hot_words", []))
        rows_html = self._rows_html(session.items[:30])

        html = HTML_TEMPLATE.format(
            platform=platform,
            keyword=keyword,
            gen_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
            total=analysis.get("total_items", len(session.items)),
            avg_likes=f"{analysis.get('avg_likes', 0):,}",
            positive_ratio=analysis.get("positive_ratio", 0),
            competition_level=analysis.get("competition_level", "-"),
            hot_words_html=hot_words_html,
            rows_html=rows_html,
        )
        path.write_text(html, encoding="utf-8")
        logger.info(f"HTML 报告已生成: {path}")
        return path

    def _hot_words_html(self, hot_words: list[tuple]) -> str:
        if not hot_words:
            return "<p>暂无热词数据</p>"
        max_count = hot_words[0][1] if hot_words else 1
        parts = []
        for word, count in hot_words[:10]:
            pct = int(count / max_count * 100)
            parts.append(
                f'<div class="bar-wrap" style="margin:8px 0">'
                f'<span style="width:80px;text-align:right;font-size:13px">{word}</span>'
                f'<div class="bar" style="width:{pct}%"></div>'
                f'<span style="font-size:12px;color:#666">{count}次</span></div>'
            )
        return "\n".join(parts)

    def _rows_html(self, items: list["ContentItem"]) -> str:
        rows = []
        for item in items:
            sent_cls = {"positive": "pos", "negative": "neg"}.get(item.sentiment_label, "neutral")
            sent_label = {"positive": "正面", "negative": "负面", "neutral": "中性"}.get(
                item.sentiment_label, item.sentiment_label)
            risk_cls = f"risk-{item.risk_level}"
            risk_label = {"high": "高", "medium": "中", "low": "低"}.get(item.risk_level, item.risk_level)
            rows.append(
                f"<tr>"
                f"<td>{item.rank}</td>"
                f"<td>{item.title[:40]}</td>"
                f"<td>{item.author}</td>"
                f"<td>{item.likes:,}</td>"
                f"<td>{item.comments:,}</td>"
                f'<td><span class="badge {sent_cls}">{sent_label}</span></td>'
                f'<td><span class="badge {risk_cls}">{risk_label}</span></td>'
                f"</tr>"
            )
        return "\n".join(rows)
