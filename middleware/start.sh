#!/usr/bin/env bash
# start.sh — 跨平台启动 middleware（macOS / Linux / Windows Git Bash）
# 用法: bash start.sh [--foreground]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_ROOT/logs/middleware.log"
PID_FILE="$PROJECT_ROOT/logs/middleware.pid"

resolve_python() {
  # 1) 优先使用项目内虚拟环境（macOS / Linux）
  if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    echo "$SCRIPT_DIR/.venv/bin/python"
    return 0
  fi

  # 2) 优先使用项目内虚拟环境（Windows / Git Bash）
  if [[ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]]; then
    echo "$SCRIPT_DIR/.venv/Scripts/python.exe"
    return 0
  fi

  # 3) 回退到系统 Python
  if command -v python3 &>/dev/null; then
    command -v python3
    return 0
  fi

  if command -v python &>/dev/null; then
    command -v python
    return 0
  fi

  echo "ERROR: No usable Python found. Please create .venv or install python3/python." >&2
  exit 1
}

PYTHON="$(resolve_python)"
mkdir -p "$(dirname "$LOG_FILE")"
cd "$SCRIPT_DIR"

echo "Using Python: $PYTHON"

if [[ "$1" == "--foreground" ]]; then
  exec "$PYTHON" main.py
fi

# 后台启动，日志追加到文件
nohup "$PYTHON" main.py >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Middleware started (PID=$(cat "$PID_FILE")), log: $LOG_FILE"
