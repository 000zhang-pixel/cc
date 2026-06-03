from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.console import Console

from drivers.ios_driver import IOSDriver
from drivers.android_driver import AndroidDriver
from drivers.windows_driver import WindowsDriver
from apps.xiaohongshu import XiaohongshuApp
from apps.douyin import DouyinApp
from apps.wechat import WechatApp
from parser.ocr_engine import OCREngine
from analysis.sentiment import SentimentAnalyzer
from analysis.ranking import RankingAnalyzer
from output.excel_writer import ExcelWriter
from output.report_generator import ReportGenerator
from models.content_item import SearchSession
from utils.helpers import format_duration
from utils.logger import log_ok, log_err, log_step

if TYPE_CHECKING:
    from config.loader import ConfigLoader

console = Console()

APP_MAP = {
    "xiaohongshu": XiaohongshuApp,
    "douyin": DouyinApp,
    "wechat": WechatApp,
}


class Orchestrator:
    def __init__(self, config: "ConfigLoader", args):
        self.config = config
        self.args = args

        self.ocr = OCREngine(
            languages=config.ocr_cfg().get("languages", ["ch_sim", "en"]),
            gpu=config.ocr_cfg().get("gpu", False),
        )
        sent_cfg = config.sentiment_cfg()
        self.sentiment = SentimentAnalyzer(
            pos_threshold=sent_cfg.get("positive_threshold", 0.6),
            neg_threshold=sent_cfg.get("negative_threshold", 0.4),
            positive_kws=sent_cfg.get("positive_keywords"),
            negative_kws=sent_cfg.get("negative_keywords"),
        )
        self.ranking = RankingAnalyzer()
        out_cfg = config.output_cfg()
        self.excel = ExcelWriter(
            output_dir=out_cfg.get("excel_dir", "output/data"),
            timestamp=out_cfg.get("timestamp_in_filename", True),
        )
        self.reporter = ReportGenerator(
            output_dir=out_cfg.get("report_dir", "output/reports"),
        )

        self.all_sessions: list[SearchSession] = []
        self.all_analyses: list[dict] = []

    # ──────────────────────────── main entry ─────────────────────────────

    def run(self) -> None:
        start = datetime.now()
        log_step("系统启动", f"平台={self.args.platform}  Apps={self.args.apps}")

        platforms = self._resolve_platforms()

        for platform_name, driver_cls, caps in platforms:
            log_step(f"连接 {platform_name} 设备")
            driver = driver_cls(self.config.appium_url(), caps)
            try:
                driver.connect()
                self._run_platform(driver, platform_name)
            except Exception as exc:
                log_err(f"{platform_name} 运行失败: {exc}")
                logger.exception(exc)
            finally:
                driver.disconnect()

        # 汇总输出
        if self.all_sessions:
            log_step("生成汇总报告")
            out = self.excel.write_multi_sessions(self.all_sessions, self.all_analyses)
            log_ok(f"汇总 Excel: {out}")

        elapsed = (datetime.now() - start).total_seconds()
        log_ok(f"全部完成，耗时 {format_duration(elapsed)}")
        self._print_summary()

    # ──────────────────────────── platform loop ──────────────────────────

    def _run_platform(self, driver, platform_name: str) -> None:
        for app_name in self.args.apps:
            app_cls = APP_MAP.get(app_name)
            if not app_cls:
                log_err(f"未知 App: {app_name}")
                continue

            app = app_cls(driver, self.config, self.ocr)
            keywords = self.args.keywords or self.config.keywords_for(app_name)

            log_step(f"[{app_name}] 共 {len(keywords)} 个关键词")

            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(), console=console
            ) as progress:
                for kw in keywords:
                    task = progress.add_task(f"搜索「{kw}」", total=None)
                    session = app.run_keyword(kw, top_n=self.args.top_n)

                    if session.items:
                        # 情感分析
                        self.sentiment.analyze_batch(session.items)
                        # 排名分析
                        analysis = self.ranking.analyze(session.items)
                        # 单次 Excel
                        self.excel.write_session(session, analysis)
                        # HTML 报告
                        self.reporter.generate(session, analysis)

                        self.all_sessions.append(session)
                        self.all_analyses.append(analysis)

                    progress.remove_task(task)
                    status = "✔" if session.success() else "✘"
                    console.print(
                        f"  {status} [{app_name}] 「{kw}」"
                        f" → {session.total_captured} 条"
                        f" 耗时 {format_duration(session.duration_seconds())}"
                    )

    # ──────────────────────────── helpers ────────────────────────────────

    def _resolve_platforms(self) -> list[tuple]:
        platforms = []

        if self.args.platform in ("ios", "both"):
            if self.args.apps:
                bundle_id = self.config.app_config(self.args.apps[0]).get(
                    "bundle_id_ios", "com.xingin.discover"
                )
                ios_caps = self.config.ios_caps(bundle_id)
            else:
                ios_caps = self.config.ios_caps("com.xingin.discover")
            platforms.append(("iOS", IOSDriver, ios_caps))

        if self.args.platform in ("android",):
            if self.args.apps:
                app_cfg = self.config.app_config(self.args.apps[0])
                package = app_cfg.get("package_android", "com.xingin.discover")
                activity = app_cfg.get("activity_android", "")
                android_caps = self.config.android_caps(package, activity)
            else:
                android_caps = self.config.android_caps("com.xingin.discover")
            platforms.append(("Android", AndroidDriver, android_caps))

        if self.args.platform in ("windows",):
            win_caps = self.config.windows_caps()
            platforms.append(("Windows", WindowsDriver, win_caps))

        return platforms

    def _print_summary(self) -> None:
        if not self.all_sessions:
            return
        table = Table(title="采集汇总", style="green")
        table.add_column("平台", style="cyan")
        table.add_column("关键词")
        table.add_column("采集条数", justify="right")
        table.add_column("正面%", justify="right")
        table.add_column("竞争等级")
        table.add_column("状态")

        for session, analysis in zip(self.all_sessions, self.all_analyses):
            table.add_row(
                session.platform,
                session.keyword,
                str(session.total_captured),
                f"{analysis.get('positive_ratio', 0)}%",
                analysis.get("competition_level", "-"),
                "[green]✔[/]" if session.success() else "[red]✘[/]",
            )
        console.print(table)
