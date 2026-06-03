#!/usr/bin/env python
"""
Appium 自动截图与舆情数据采集系统
Usage:
    python main.py --platform ios --apps xiaohongshu douyin --top-n 30
    python main.py --platform ios --apps xiaohongshu --keywords 护肤品推荐 平价美妆
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 保证在任意工作目录下都能找到模块
sys.path.insert(0, str(Path(__file__).parent))

from config.loader import ConfigLoader
from core.orchestrator import Orchestrator
from utils.logger import setup_logger


def parse_args():
    parser = argparse.ArgumentParser(
        description="Appium 自动截图 & 舆情统计系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # iOS 小红书 TOP30
  python main.py --platform ios --apps xiaohongshu --top-n 30

  # iOS 抖音+小红书，指定关键词
  python main.py --platform ios --apps xiaohongshu douyin \\
      --keywords "护肤品推荐" "平价美妆"

  # 读取 config/keywords.yaml 中所有关键词，iOS+Windows
  python main.py --platform both --apps xiaohongshu douyin wechat
""",
    )
    parser.add_argument(
        "--platform",
        choices=["ios", "android", "windows"],
        default="android",
        help="目标平台（默认 android）",
    )
    parser.add_argument(
        "--apps",
        nargs="+",
        choices=["xiaohongshu", "douyin", "wechat"],
        default=["xiaohongshu"],
        metavar="APP",
        help="要搜索的 App（可多选）",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        metavar="KW",
        help="搜索关键词（不指定则读 config/keywords.yaml）",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="每个关键词采集 TOP N 条（不指定则用 settings.yaml 里的 max_results）",
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="settings.yaml 路径",
    )
    parser.add_argument(
        "--keywords-file",
        default="config/keywords.yaml",
        help="keywords.yaml 路径",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logger(level=args.log_level)

    config = ConfigLoader(args.config, args.keywords_file)
    orchestrator = Orchestrator(config, args)
    orchestrator.run()


if __name__ == "__main__":
    main()
