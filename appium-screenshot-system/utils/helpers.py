from __future__ import annotations

import re
import time
import functools
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")


def parse_count(text: str) -> int:
    """解析中文社交媒体数字格式，如 '1.2万'→12000，'3.8k'→3800，'2.1亿'→210000000"""
    if not text:
        return 0
    text = text.strip().replace(",", "").replace("，", "")
    multipliers = {"万": 10000, "亿": 100000000, "k": 1000, "K": 1000, "w": 10000, "W": 10000}
    for suffix, mult in multipliers.items():
        if suffix in text:
            num_str = text.replace(suffix, "").strip()
            try:
                return int(float(num_str) * mult)
            except ValueError:
                return 0
    try:
        return int(float(re.sub(r"[^\d.]", "", text)))
    except ValueError:
        return 0


def safe_filename(name: str, max_len: int = 60) -> str:
    """将关键词/标题转为安全文件名"""
    name = re.sub(r'[\\/:*?"<>|\s]', "_", name)
    return name[:max_len]


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def retry(max_attempts: int = 3, delay: float = 1.5, exceptions: tuple = (Exception,)):
    """重试装饰器，适用于不稳定的 Appium 操作"""
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        time.sleep(delay * attempt)
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator


def chunk_list(lst: list, size: int) -> list[list]:
    return [lst[i: i + size] for i in range(0, len(lst), size)]


def format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}分{s}秒" if m else f"{s}秒"
