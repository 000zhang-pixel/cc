from __future__ import annotations

import sys
from pathlib import Path
from loguru import logger
from rich.console import Console
from rich.theme import Theme

console = Console(theme=Theme({
    "info": "cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
}))


def setup_logger(log_dir: str = "output/logs", level: str = "INFO") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
    logger.add(
        Path(log_dir) / "app_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="14 days",
        level="DEBUG",
        encoding="utf-8",
    )


def log_step(step: str, detail: str = "") -> None:
    msg = f"[bold cyan]▶ {step}[/]"
    if detail:
        msg += f"  [dim]{detail}[/]"
    console.print(msg)


def log_ok(msg: str) -> None:
    console.print(f"[success]✔ {msg}[/]")


def log_warn(msg: str) -> None:
    console.print(f"[warning]⚠ {msg}[/]")


def log_err(msg: str) -> None:
    console.print(f"[error]✘ {msg}[/]")
