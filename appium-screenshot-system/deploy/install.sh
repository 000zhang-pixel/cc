#!/bin/bash
# Appium 截图 & 舆情系统 —— macOS 一键安装脚本
# 用法: bash deploy/install.sh

set -e
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✔]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
err()  { echo -e "${RED}[✘]${NC} $1"; exit 1; }
info() { echo -e "${BLUE}[→]${NC} $1"; }
step() { echo; echo -e "${BLUE}━━ $1 ━━${NC}"; }

echo
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Appium 自动截图 & 舆情统计系统  ——  macOS 安装器    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "  项目目录: $PROJECT_DIR"

# ── 1. Xcode Command Line Tools ─────────────────────────────────
step "1/8  Xcode Command Line Tools"
if xcode-select -p &>/dev/null; then
    ok "Xcode CLT 已安装: $(xcode-select -p)"
else
    info "安装 Xcode Command Line Tools..."
    xcode-select --install
    echo "  安装完成后，重新运行本脚本"
    exit 0
fi

# ── 2. Homebrew ──────────────────────────────────────────────────
step "2/8  Homebrew"
if command -v brew &>/dev/null; then
    ok "Homebrew $(brew --version | head -1)"
else
    info "安装 Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/homebrew/install/HEAD/install.sh)"
    # Apple Silicon 路径修正
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
    ok "Homebrew 安装完成"
fi

# ── 3. Node.js ───────────────────────────────────────────────────
step "3/8  Node.js"
if command -v node &>/dev/null; then
    ok "Node.js $(node --version)"
else
    info "安装 Node.js LTS..."
    brew install node
    ok "Node.js $(node --version)"
fi

# ── 4. Python 3.11+ ─────────────────────────────────────────────
step "4/8  Python"
PY_CMD=""
for cmd in python3.11 python3.12 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(sys.version_info[:2])" 2>/dev/null)
        if [[ "$ver" > "(3, 8)" ]]; then
            PY_CMD="$cmd"
            ok "Python: $($PY_CMD --version)  [$PY_CMD]"
            break
        fi
    fi
done
if [ -z "$PY_CMD" ]; then
    info "安装 Python 3.11..."
    brew install python@3.11
    PY_CMD="python3.11"
    ok "Python: $($PY_CMD --version)"
fi

# ── 5. 虚拟环境 & Python 依赖 ────────────────────────────────────
step "5/8  Python 虚拟环境 & 依赖"
if [ ! -d ".venv" ]; then
    info "创建虚拟环境..."
    $PY_CMD -m venv .venv
    ok "虚拟环境已创建: .venv/"
else
    ok ".venv/ 已存在，跳过创建"
fi

source .venv/bin/activate
info "升级 pip..."
pip install --upgrade pip -q

info "安装 Python 依赖（首次约 3-5 分钟）..."
# 先装不需要编译的包
pip install Appium-Python-Client selenium Pillow numpy pandas openpyxl \
    pyyaml loguru rich pytest pytest-mock -q
ok "核心依赖安装完成"

# snownlp 需要 C 编译器，单独处理
if pip install snownlp -q 2>/dev/null; then
    ok "snownlp（中文情感分析）安装完成"
else
    warn "snownlp 安装失败，将使用关键词规则分析（功能不受影响）"
fi

# easyocr 体积大，单独安装
info "安装 easyocr（OCR 引擎，约 200MB）..."
if pip install easyocr -q 2>/dev/null; then
    ok "easyocr 安装完成"
else
    warn "easyocr 安装失败，OCR 回退功能不可用（主功能不受影响）"
fi

# ── 6. Appium & 驱动 ─────────────────────────────────────────────
step "6/8  Appium"
if command -v appium &>/dev/null; then
    ok "Appium $(appium --version) 已安装"
else
    info "全局安装 Appium..."
    npm install -g appium
    ok "Appium $(appium --version) 安装完成"
fi

info "安装 XCUITest 驱动（iOS 自动化）..."
if appium driver list --installed 2>/dev/null | grep -q xcuitest; then
    ok "xcuitest 驱动已安装"
else
    appium driver install xcuitest
    ok "xcuitest 驱动安装完成"
fi

# ── 7. iOS 设备工具 ──────────────────────────────────────────────
step "7/8  iOS 设备工具"
for pkg in libimobiledevice ideviceinstaller ios-deploy; do
    if brew list "$pkg" &>/dev/null; then
        ok "$pkg 已安装"
    else
        info "安装 $pkg..."
        brew install "$pkg" 2>/dev/null || warn "$pkg 安装失败（可忽略）"
    fi
done

# ── 8. 创建输出目录 & 运行测试 ───────────────────────────────────
step "8/8  目录初始化 & 测试"
for d in output/screenshots output/data output/reports output/logs output/mock_data output/mock_reports; do
    mkdir -p "$d"
done
ok "输出目录就绪"

info "运行离线单元测试..."
python -m pytest tests/ -q --tb=short 2>/dev/null && ok "全部测试通过" || warn "部分测试未通过，请检查依赖"

info "运行 Mock 端到端测试（无需真机）..."
python tools/mock_run.py 2>/dev/null && ok "Mock 测试通过，Excel & HTML 报告已生成" || warn "Mock 测试失败"

# ── 完成提示 ────────────────────────────────────────────────────
echo
echo "══════════════════════════════════════════════════════"
echo "  ✅ 安装完成！接下来："
echo
echo "  【第一次使用 · 必做】校准元素定位器"
echo "    1. 用 USB 连接 iPhone"
echo "    2. 在另一个终端启动 Appium："
echo "         appium --address 0.0.0.0 --port 4723"
echo "    3. 用 idevice_id -l 查询设备 UDID，填入 config/settings.yaml"
echo "    4. bash deploy/calibrate.sh xiaohongshu"
echo
echo "  【日常使用】"
echo "    bash deploy/run.sh                          # 默认：小红书 TOP30"
echo "    bash deploy/run.sh xiaohongshu douyin       # 多 App"
echo "    bash deploy/run.sh xiaohongshu --top-n 20 --keywords '护肤品推荐'"
echo
echo "  【离线测试（无需设备）】"
echo "    source .venv/bin/activate"
echo "    python tools/mock_run.py"
echo "══════════════════════════════════════════════════════"
echo
