"""
Config loader — reads system.yaml and model_params.yaml,
expanding ${ENV_VAR} references from environment / .env file.
"""
import os
import re
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level above middleware/)
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=False)


def _expand_env(obj):
    """Recursively expand ${VAR} in string values."""
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    if isinstance(obj, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    return obj


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _expand_env(raw)


_CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_system() -> dict:
    return _load(_CONFIG_DIR / "system.yaml")


def load_model_params() -> dict:
    return _load(_CONFIG_DIR / "model_params.yaml")
