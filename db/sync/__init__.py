"""
db/sync package — Feishu → local SQLite incremental sync.
"""
from .syncer import FeishuSyncer

__all__ = ["FeishuSyncer"]
