#!/bin/bash
# 环境检查：显示所有依赖状态
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✔${NC}  $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $1"; }
fail() { echo -e "  ${RED}✘${NC}  $1"; }

echo
echo "━━ 环境检查 ━━"
echo

# Python
if command -v python3 &>/dev/null; then
    ok "Python: $(python3 --version)"
else
    fail "Python3 未安装"
fi

# 虚拟环境
if [ -d ".venv" ]; then
    ok ".venv 虚拟环境存在"
else
    warn ".venv 不存在（请先运行 bash deploy/install.sh）"
fi

# Python 包
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    for pkg in appium selenium PIL pandas openpyxl loguru rich; do
        python -c "import $pkg" 2>/dev/null && ok "Python: $pkg" || fail "Python: $pkg 未安装"
    done
    python -c "import snownlp" 2>/dev/null && ok "Python: snownlp（情感分析）" || warn "Python: snownlp 未安装（用关键词规则替代）"
    python -c "import easyocr" 2>/dev/null && ok "Python: easyocr（OCR）" || warn "Python: easyocr 未安装（OCR 功能不可用）"
fi

echo
# Node / npm
command -v node &>/dev/null && ok "Node.js: $(node --version)" || fail "Node.js 未安装"
command -v npm &>/dev/null && ok "npm: $(npm --version)" || fail "npm 未安装"

echo
# Appium
if command -v appium &>/dev/null; then
    ok "Appium: $(appium --version)"
    appium driver list --installed 2>/dev/null | grep -q xcuitest && ok "Appium driver: xcuitest" || warn "Appium driver: xcuitest 未安装"
    appium driver list --installed 2>/dev/null | grep -q windows && ok "Appium driver: windows" || warn "Appium driver: windows 未安装"
else
    fail "Appium 未安装（npm install -g appium）"
fi

echo
# Appium 运行状态
if curl -s http://localhost:4723/status &>/dev/null; then
    ok "Appium Server 运行中（localhost:4723）"
else
    warn "Appium Server 未运行（运行: appium --port 4723）"
fi

echo
# iOS 工具
command -v idevice_id &>/dev/null && ok "libimobiledevice 已安装" || warn "libimobiledevice 未安装（brew install libimobiledevice）"
command -v ios-deploy &>/dev/null && ok "ios-deploy 已安装" || warn "ios-deploy 未安装（brew install ios-deploy）"

# iOS 设备
UDID=$(idevice_id -l 2>/dev/null | head -1)
if [ -n "$UDID" ]; then
    ok "iOS 设备已连接: $UDID"
else
    warn "未检测到 iOS 设备（请连接 iPhone 并解锁）"
fi

echo
# Xcode
if xcode-select -p &>/dev/null; then
    ok "Xcode CLT: $(xcode-select -p)"
else
    fail "Xcode Command Line Tools 未安装"
fi

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
