#!/usr/bin/env bash
# start.sh — 跨平台启动 middleware（Mac / Windows Git Bash）
# 用法: bash start.sh [--foreground]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$(dirname "$SCRIPT_DIR")/logs/middleware.log"
PID_FILE="$(dirname "$SCRIPT_DIR")/logs/middleware.pid"

# 找 Python（优先 python3，兼容 Windows python）
if command -v python3 &>/dev/null; then
  PYTHON=python3
elif command -v python &>/dev/null; then
  PYTHON=python
else
  echo "ERROR: python3 / python not found in PATH" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")"

if [[ "$1" == "--foreground" ]]; then
  cd "$SCRIPT_DIR"
  exec "$PYTHON" main.py
fi

# 后台启动，日志追加到文件
cd "$SCRIPT_DIR"
nohup "$PYTHON" main.py >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Middleware started (PID=$(cat $PID_FILE)), log: $LOG_FILE"
