#!/usr/bin/env bash
# setup_autostart_mac.sh — 在 macOS 上用 launchd 注册开机自启
# 用法: bash setup_autostart_mac.sh

MIDDLEWARE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$MIDDLEWARE_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
PLIST_LABEL="com.ai-content-hub.middleware"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

# 找 Python
if command -v python3 &>/dev/null; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "ERROR: python3 not found" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$PLIST_LABEL</string>

  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$MIDDLEWARE_DIR/main.py</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$MIDDLEWARE_DIR</string>

  <key>StandardOutPath</key>
  <string>$LOG_DIR/middleware.log</string>

  <key>StandardErrorPath</key>
  <string>$LOG_DIR/middleware.log</string>

  <!-- 登录后自动启动 -->
  <key>RunAtLoad</key>
  <true/>

  <!-- 崩溃后 5 秒自动重启 -->
  <key>KeepAlive</key>
  <dict>
    <key>Crashed</key>
    <true/>
  </dict>
  <key>ThrottleInterval</key>
  <integer>5</integer>
</dict>
</plist>
EOF

# 加载（立即生效，无需重启）
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "已注册 launchd 服务: $PLIST_LABEL"
echo "日志: $LOG_DIR/middleware.log"
echo ""
echo "常用命令:"
echo "  launchctl stop  $PLIST_LABEL   # 停止"
echo "  launchctl start $PLIST_LABEL   # 启动"
echo "  launchctl unload $PLIST_PATH    # 彻底移除自启"
