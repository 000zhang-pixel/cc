#!/bin/bash
# 启动截图采集任务
# 用法示例:
#   bash deploy/run.sh                                          # 默认：小红书 TOP30
#   bash deploy/run.sh xiaohongshu douyin                      # 多 App
#   bash deploy/run.sh xiaohongshu --top-n 20                  # 指定数量
#   bash deploy/run.sh xiaohongshu --keywords "护肤品推荐" "好物分享"

set -e
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'

# 激活虚拟环境
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo -e "${YELLOW}[⚠]${NC} 未找到 .venv，请先运行 bash deploy/install.sh"
    exit 1
fi

# 解析首批参数作为 App 列表（不含 -- 前缀的视为 app 名称）
APPS=""
EXTRA_ARGS=""
for arg in "$@"; do
    if [[ "$arg" == xiaohongshu || "$arg" == douyin || "$arg" == wechat ]]; then
        APPS="$APPS $arg"
    else
        EXTRA_ARGS="$EXTRA_ARGS $arg"
    fi
done

[ -z "$APPS" ] && APPS="xiaohongshu"

echo
echo -e "${BLUE}━━ 启动 Appium 截图系统 ━━${NC}"
echo -e "  Apps  : ${APPS# }"
echo -e "  参数  : ${EXTRA_ARGS# }"
echo

# 检查 Appium 是否已在运行
if curl -s http://localhost:4723/status &>/dev/null; then
    echo -e "${GREEN}[✔]${NC} Appium Server 已在运行（localhost:4723）"
else
    echo -e "${YELLOW}[⚠]${NC} Appium 未运行，自动在后台启动..."
    appium --address 0.0.0.0 --port 4723 --log output/logs/appium.log &
    APPIUM_PID=$!
    echo "     PID: $APPIUM_PID  日志: output/logs/appium.log"
    sleep 3
    if ! curl -s http://localhost:4723/status &>/dev/null; then
        echo -e "${RED}[✘]${NC} Appium 启动失败，请手动运行: appium --port 4723"
        exit 1
    fi
    echo -e "${GREEN}[✔]${NC} Appium 已启动"
fi

echo
python main.py --platform ios --apps $APPS $EXTRA_ARGS

echo
echo -e "${GREEN}━━ 任务完成 ━━${NC}"
echo "  📊 Excel 数据  : output/data/"
echo "  📄 HTML 报告   : output/reports/"
echo "  🖼  长截图      : output/screenshots/"
echo
