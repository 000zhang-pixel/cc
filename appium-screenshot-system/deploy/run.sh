#!/bin/bash
# 启动截图采集任务
#
# 用法示例:
#   bash deploy/run.sh                                         # Android 小红书 TOP30（默认）
#   bash deploy/run.sh --platform android xiaohongshu douyin  # Android 多 App
#   bash deploy/run.sh --platform ios xiaohongshu             # iOS
#   bash deploy/run.sh --platform android xiaohongshu --top-n 20
#   bash deploy/run.sh --platform android xiaohongshu --keywords "护肤品推荐" "好物分享"

set -e
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'

[ -f ".venv/bin/activate" ] && source .venv/bin/activate \
    || { echo -e "${YELLOW}[⚠]${NC} 未找到 .venv，请先运行 bash deploy/install.sh"; exit 1; }

# ── 解析参数 ─────────────────────────────────────────────────────
PLATFORM="android"    # 默认 Android
APPS=""
EXTRA_ARGS=""

for arg in "$@"; do
    case "$arg" in
        --platform) : ;;               # 由下一个参数捕获
        android|ios|windows)
            # 如果上一个 arg 是 --platform 则设平台，否则视为 app 名
            if [[ "${PREV_ARG:-}" == "--platform" ]]; then
                PLATFORM="$arg"
            else
                APPS="$APPS $arg"
            fi
            ;;
        xiaohongshu|douyin|wechat) APPS="$APPS $arg" ;;
        *) EXTRA_ARGS="$EXTRA_ARGS $arg" ;;
    esac
    PREV_ARG="$arg"
done

# 重新解析 --platform 值（兼容 --platform android 写法）
REBUILD_ARGS=()
SKIP_NEXT=false
for arg in "$@"; do
    if $SKIP_NEXT; then SKIP_NEXT=false; continue; fi
    if [[ "$arg" == "--platform" ]]; then
        SKIP_NEXT=true
        continue
    fi
    REBUILD_ARGS+=("$arg")
done

# 用 Python argparse 处理更可靠，直接透传所有参数
echo
echo -e "${BLUE}━━ 启动 Appium 截图系统 ━━${NC}"

# ── 检查设备 ──────────────────────────────────────────────────────
DETECTED_PLATFORM=""
if [[ "$*" == *"--platform android"* ]] || [[ "$*" != *"--platform"* ]]; then
    ANDROID_SERIAL=$(adb devices 2>/dev/null | awk 'NR>1 && /device$/{print $1; exit}')
    if [ -n "$ANDROID_SERIAL" ]; then
        DETECTED_PLATFORM="android"
        echo -e "  ${GREEN}[✔]${NC} Android 设备: $ANDROID_SERIAL"
    fi
fi
if [[ "$*" == *"--platform ios"* ]]; then
    IOS_UDID=$(idevice_id -l 2>/dev/null | head -1)
    [ -n "$IOS_UDID" ] && echo -e "  ${GREEN}[✔]${NC} iOS 设备: $IOS_UDID"
fi

# ── 自动启动 Appium ──────────────────────────────────────────────
if curl -s http://localhost:4723/status &>/dev/null; then
    echo -e "  ${GREEN}[✔]${NC} Appium Server 运行中（localhost:4723）"
else
    echo -e "  ${YELLOW}[⚠]${NC} Appium 未运行，后台启动中..."
    appium --address 0.0.0.0 --port 4723 --log output/logs/appium.log &
    APPIUM_PID=$!
    sleep 3
    if ! curl -s http://localhost:4723/status &>/dev/null; then
        echo -e "  ${RED}[✘]${NC} Appium 启动失败，请手动运行: appium --port 4723"
        exit 1
    fi
    echo -e "  ${GREEN}[✔]${NC} Appium 已启动 (PID=$APPIUM_PID)"
fi

echo
# 透传所有参数给 main.py，若没有 --platform 参数，默认传 android
if [[ "$*" != *"--platform"* ]]; then
    python main.py --platform android "$@"
else
    python main.py "$@"
fi

echo
echo -e "${GREEN}━━ 任务完成 ━━${NC}"
echo -e "  📊 Excel  : output/data/"
echo -e "  📄 报告   : output/reports/"
echo -e "  🖼  截图   : output/screenshots/"
echo
