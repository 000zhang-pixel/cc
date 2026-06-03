#!/bin/bash
# 环境全面检查
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✔${NC}  $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $1"; }
fail() { echo -e "  ${RED}✘${NC}  $1"; }

echo
echo "━━ 系统 & 工具 ━━"
command -v brew &>/dev/null && ok "Homebrew: $(brew --version | head -1)" || fail "Homebrew 未安装"
command -v node &>/dev/null && ok "Node.js: $(node --version)" || fail "Node.js 未安装"
xcode-select -p &>/dev/null && ok "Xcode CLT: $(xcode-select -p)" || fail "Xcode CLT 未安装"

echo
echo "━━ Python ━━"
[ -d ".venv" ] && ok ".venv 虚拟环境存在" || warn ".venv 不存在（请运行 bash deploy/install.sh）"
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    ok "Python: $(python --version)"
    for pkg in appium selenium PIL pandas openpyxl loguru rich yaml; do
        python -c "import $pkg" 2>/dev/null && ok "  $pkg" || fail "  $pkg 未安装"
    done
    python -c "import snownlp" 2>/dev/null && ok "  snownlp（情感分析）" || warn "  snownlp 未装（用规则替代）"
    python -c "import easyocr"  2>/dev/null && ok "  easyocr（OCR）"     || warn "  easyocr 未装（OCR 不可用）"
fi

echo
echo "━━ Appium ━━"
if command -v appium &>/dev/null; then
    ok "Appium: $(appium --version)"
    appium driver list --installed 2>/dev/null | grep -q uiautomator2 \
        && ok "  驱动: uiautomator2 (Android)" || warn "  驱动: uiautomator2 未安装 → appium driver install uiautomator2"
    appium driver list --installed 2>/dev/null | grep -q xcuitest \
        && ok "  驱动: xcuitest (iOS)" || warn "  驱动: xcuitest 未安装 → appium driver install xcuitest"
else
    fail "Appium 未安装（npm install -g appium）"
fi

curl -s http://localhost:4723/status &>/dev/null \
    && ok "Appium Server 运行中（:4723）" || warn "Appium Server 未运行（appium --port 4723）"

echo
echo "━━ Android / 小米 ━━"
if command -v adb &>/dev/null; then
    ok "adb: $(adb version | head -1)"
    SERIAL=$(adb devices 2>/dev/null | awk 'NR>1 && /device$/{print $1; exit}')
    if [ -n "$SERIAL" ]; then
        MODEL=$(adb -s "$SERIAL" shell getprop ro.product.model 2>/dev/null | tr -d '\r')
        AVER=$(adb -s "$SERIAL" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')
        ok "设备已连接: $SERIAL  [$MODEL  Android $AVER]"
        # 检查 USB 调试状态
        DEBUG=$(adb -s "$SERIAL" shell settings get global adb_enabled 2>/dev/null | tr -d '\r')
        [ "$DEBUG" = "1" ] && ok "USB 调试已开启" || warn "USB 调试状态未知"
        # 检查 settings.yaml 中的 UDID 是否匹配
        CFG_UDID=$(python -c "import yaml; c=yaml.safe_load(open('config/settings.yaml')); print(c.get('android',{}).get('udid',''))" 2>/dev/null)
        if [ "$CFG_UDID" = "$SERIAL" ]; then
            ok "settings.yaml UDID 已配置 ✔"
        else
            warn "settings.yaml android.udid=\"$CFG_UDID\"（当前设备 $SERIAL，运行 calibrate.sh 更新）"
        fi
    else
        warn "未检测到 Android 设备（连接手机 USB，选「文件传输」，允许 USB 调试）"
    fi
else
    fail "adb 未安装（brew install android-platform-tools）"
fi

echo
echo "━━ iOS（可选）━━"
command -v idevice_id &>/dev/null && ok "libimobiledevice 已安装" || warn "libimobiledevice 未安装（brew install libimobiledevice）"
UDID=$(idevice_id -l 2>/dev/null | head -1)
[ -n "$UDID" ] && ok "iOS 设备已连接: $UDID" || warn "未检测到 iOS 设备"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
