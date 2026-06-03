#!/bin/bash
# 元素定位器校准 —— 自动检测 Android/iOS 设备，打印页面元素树
#
# 用法:
#   bash deploy/calibrate.sh --android xiaohongshu   # Android/小米
#   bash deploy/calibrate.sh --ios xiaohongshu        # iOS
#   bash deploy/calibrate.sh xiaohongshu              # 自动检测

set -e
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✔]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
info() { echo -e "${BLUE}[→]${NC} $1"; }

# 解析参数
PLATFORM=""
APP="xiaohongshu"
for arg in "$@"; do
    case "$arg" in
        --android) PLATFORM="android" ;;
        --ios)     PLATFORM="ios" ;;
        xiaohongshu|douyin|wechat) APP="$arg" ;;
    esac
done

# ── 自动检测平台 ─────────────────────────────────────────────────
if [ -z "$PLATFORM" ]; then
    ANDROID_SERIAL=$(adb devices 2>/dev/null | awk 'NR>1 && /device$/{print $1; exit}')
    IOS_UDID=$(idevice_id -l 2>/dev/null | head -1)
    if [ -n "$ANDROID_SERIAL" ]; then
        PLATFORM="android"
        info "自动检测到 Android 设备: $ANDROID_SERIAL"
    elif [ -n "$IOS_UDID" ]; then
        PLATFORM="ios"
        info "自动检测到 iOS 设备: $IOS_UDID"
    else
        echo -e "${RED}[✘]${NC} 未检测到任何设备，请连接手机后重试"
        exit 1
    fi
fi

echo
echo -e "${BLUE}━━ 元素校准  |  平台: $PLATFORM  App: $APP ━━${NC}"
echo

# 激活虚拟环境
[ -f ".venv/bin/activate" ] && source .venv/bin/activate

# ── Android 设备处理 ─────────────────────────────────────────────
if [ "$PLATFORM" = "android" ]; then
    SERIAL=$(adb devices 2>/dev/null | awk 'NR>1 && /device$/{print $1; exit}')
    if [ -z "$SERIAL" ]; then
        echo -e "${RED}[✘]${NC} 未检测到 Android 设备，请确认："
        echo "     1. 小米手机已开启 USB 调试"
        echo "     2. USB 连接并选择「文件传输」模式"
        echo "     3. 手机屏幕弹出「允许 USB 调试」，点击允许"
        echo "     提示：运行 adb devices 查看状态"
        exit 1
    fi
    ok "Android 设备: $SERIAL"

    # 设备信息
    MODEL=$(adb -s "$SERIAL" shell getprop ro.product.model 2>/dev/null | tr -d '\r')
    ANDROID_VER=$(adb -s "$SERIAL" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')
    ok "型号: $MODEL  Android: $ANDROID_VER"

    # 自动写入 settings.yaml
    if python -c "
import yaml, pathlib
cfg = yaml.safe_load(pathlib.Path('config/settings.yaml').read_text())
cfg['android']['udid'] = '$SERIAL'
cfg['android']['platform_version'] = '$ANDROID_VER'
pathlib.Path('config/settings.yaml').write_text(yaml.dump(cfg, allow_unicode=True, default_flow_style=False))
print('OK')
" 2>/dev/null; then
        ok "UDID 和系统版本已自动写入 config/settings.yaml"
    else
        warn "自动写入失败，请手动将以下值填入 config/settings.yaml → android:"
        echo "     udid: \"$SERIAL\""
        echo "     platform_version: \"$ANDROID_VER\""
    fi

# ── iOS 设备处理 ─────────────────────────────────────────────────
else
    UDID=$(idevice_id -l 2>/dev/null | head -1)
    if [ -z "$UDID" ]; then
        echo -e "${RED}[✘]${NC} 未检测到 iOS 设备"
        exit 1
    fi
    ok "iOS 设备: $UDID"

    if grep -q 'udid: ""' config/settings.yaml; then
        sed -i '' "s|udid: \"\"|udid: \"$UDID\"|g" config/settings.yaml
        ok "UDID 已写入 config/settings.yaml"
    fi
fi

# ── 启动 Appium ──────────────────────────────────────────────────
if ! curl -s http://localhost:4723/status &>/dev/null; then
    info "Appium 未运行，后台启动中..."
    appium --address 0.0.0.0 --port 4723 --log output/logs/appium_calibrate.log &
    sleep 4
    curl -s http://localhost:4723/status &>/dev/null && ok "Appium 已启动" || { echo -e "${RED}[✘]${NC} Appium 启动失败"; exit 1; }
else
    ok "Appium 已在运行"
fi

# ── 运行校准工具 ─────────────────────────────────────────────────
echo
echo -e "${BLUE}━━ 启动校准工具 ━━${NC}"
echo "  请在手机上手动导航到「${APP}搜索结果页」，"
echo "  然后回到此终端按 Enter，打印页面元素树。"
echo
python tools/calibrate_locators.py --platform "$PLATFORM" --app "$APP"

echo
echo -e "${GREEN}━━ 校准完成 ━━${NC}"
echo "  元素树已保存到 output/page_source.xml"
echo "  根据打印的 text/content-desc/resource-id 更新 config/settings.yaml"
echo "  重点检查 locators.${PLATFORM} 下各 App 的 search_button / result_item"
echo
