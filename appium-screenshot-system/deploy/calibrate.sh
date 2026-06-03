#!/bin/bash
# 元素定位器校准：连接真机后，打印页面元素树，帮助更新 settings.yaml
# 用法: bash deploy/calibrate.sh [xiaohongshu|douyin|wechat]

set -e
cd "$(dirname "$0")/.."

APP="${1:-xiaohongshu}"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

if [ -f ".venv/bin/activate" ]; then source .venv/bin/activate; fi

echo
echo -e "${BLUE}━━ 元素定位器校准  |  App: $APP ━━${NC}"
echo

# 检测连接的 iOS 设备
echo -e "${BLUE}[→]${NC} 检测 iOS 设备..."
UDID=$(idevice_id -l 2>/dev/null | head -1)
if [ -z "$UDID" ]; then
    echo -e "${YELLOW}[⚠]${NC} 未检测到 iOS 设备"
    echo "     请确认："
    echo "     1. iPhone 已通过 USB 连接"
    echo "     2. 手机已解锁并信任此电脑"
    echo "     3. 已安装 libimobiledevice（brew install libimobiledevice）"
    exit 1
fi
echo -e "${GREEN}[✔]${NC} 设备 UDID: $UDID"

# 自动写入 settings.yaml
if grep -q 'udid: ""' config/settings.yaml; then
    sed -i '' "s|udid: \"\"|udid: \"$UDID\"|g" config/settings.yaml
    echo -e "${GREEN}[✔]${NC} UDID 已自动写入 config/settings.yaml"
else
    echo -e "${YELLOW}[⚠]${NC} settings.yaml 中 UDID 已有值，跳过自动写入"
fi

# 检查 Appium
if ! curl -s http://localhost:4723/status &>/dev/null; then
    echo -e "${YELLOW}[⚠]${NC} Appium 未运行，后台启动中..."
    appium --address 0.0.0.0 --port 4723 --log output/logs/appium_calibrate.log &
    sleep 4
fi

echo
echo -e "${BLUE}━━ 启动校准工具 ━━${NC}"
echo "  请在手机上手动导航到目标页面（如小红书搜索结果页），"
echo "  然后回到此终端按 Enter，系统将打印当前页面的元素树。"
echo
python tools/calibrate_locators.py --app "$APP"

echo
echo -e "${GREEN}━━ 校准完成 ━━${NC}"
echo "  元素树已保存到  output/page_source.xml"
echo "  根据打印的 label/name，更新 config/settings.yaml 中对应 app 的 locators"
echo
