#!/bin/bash
# Appium 截图 & 舆情系统 —— macOS 一键安装脚本（支持 iOS + Android/小米）
# 用法: bash deploy/install.sh

set -e
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✔]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
err()  { echo -e "${RED}[✘]${NC} $1"; exit 1; }
info() { echo -e "${BLUE}[→]${NC} $1"; }
step() { echo; echo -e "${BLUE}━━ $1 ━━${NC}"; }

echo
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Appium 自动截图 & 舆情统计系统  ——  macOS 安装器       ║"
echo "║   支持平台: Android/小米 · iOS · Windows                  ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ── 1. Xcode CLT ────────────────────────────────────────────────
step "1/9  Xcode Command Line Tools"
if xcode-select -p &>/dev/null; then
    ok "Xcode CLT: $(xcode-select -p)"
else
    info "安装 Xcode Command Line Tools..."
    xcode-select --install
    echo "  安装完成后重新运行本脚本"
    exit 0
fi

# ── 2. Homebrew ──────────────────────────────────────────────────
step "2/9  Homebrew"
if command -v brew &>/dev/null; then
    ok "Homebrew $(brew --version | head -1)"
else
    info "安装 Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/homebrew/install/HEAD/install.sh)"
    [[ -f /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)" && \
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    ok "Homebrew 安装完成"
fi

# ── 3. Node.js ───────────────────────────────────────────────────
step "3/9  Node.js"
if command -v node &>/dev/null; then
    ok "Node.js $(node --version)"
else
    info "安装 Node.js LTS..."
    brew install node
    ok "Node.js $(node --version)"
fi

# ── 4. Python ────────────────────────────────────────────────────
step "4/9  Python"
PY_CMD=""
for cmd in python3.11 python3.12 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(sys.version_info >= (3,9))" 2>/dev/null)
        if [[ "$ver" == "True" ]]; then
            PY_CMD="$cmd"; ok "Python: $($PY_CMD --version)  [$PY_CMD]"; break
        fi
    fi
done
if [ -z "$PY_CMD" ]; then
    info "安装 Python 3.11..."
    brew install python@3.11
    PY_CMD="python3.11"; ok "Python: $($PY_CMD --version)"
fi

# ── 5. 虚拟环境 & Python 依赖 ────────────────────────────────────
step "5/9  Python 虚拟环境 & 依赖"
if [ ! -d ".venv" ]; then
    $PY_CMD -m venv .venv && ok ".venv/ 创建完成"
else
    ok ".venv/ 已存在"
fi

source .venv/bin/activate
pip install --upgrade pip -q

info "安装核心依赖..."
pip install Appium-Python-Client selenium Pillow numpy pandas openpyxl \
    pyyaml loguru rich pytest pytest-mock -q
ok "核心依赖安装完成"

pip install snownlp -q 2>/dev/null \
    && ok "snownlp（情感分析）" \
    || warn "snownlp 安装失败，使用关键词规则替代"

info "安装 easyocr（约 200MB，可选）..."
pip install easyocr -q 2>/dev/null \
    && ok "easyocr（OCR 引擎）" \
    || warn "easyocr 安装失败，OCR 回退功能不可用"

# ── 6. Appium & 驱动 ─────────────────────────────────────────────
step "6/9  Appium"
if ! command -v appium &>/dev/null; then
    info "全局安装 Appium..."
    npm install -g appium && ok "Appium $(appium --version)"
else
    ok "Appium $(appium --version) 已安装"
fi

# Android 驱动（UIAutomator2）—— 小米必需
info "安装 UiAutomator2 驱动（Android/小米）..."
if appium driver list --installed 2>/dev/null | grep -q uiautomator2; then
    ok "uiautomator2 驱动已安装"
else
    appium driver install uiautomator2 && ok "uiautomator2 安装完成"
fi

# iOS 驱动（XCUITest）
info "安装 XCUITest 驱动（iOS，可选）..."
if appium driver list --installed 2>/dev/null | grep -q xcuitest; then
    ok "xcuitest 驱动已安装"
else
    appium driver install xcuitest && ok "xcuitest 安装完成"
fi

# ── 7. Android 工具（adb / platform-tools）──────────────────────
step "7/9  Android 工具"
if command -v adb &>/dev/null; then
    ok "adb $(adb version | head -1)"
else
    info "安装 Android Platform Tools（含 adb）..."
    brew install android-platform-tools
    ok "adb $(adb version | head -1)"
fi

# ── 8. iOS 工具（可选）──────────────────────────────────────────
step "8/9  iOS 设备工具（可选）"
for pkg in libimobiledevice ideviceinstaller; do
    brew list "$pkg" &>/dev/null \
        && ok "$pkg 已安装" \
        || { brew install "$pkg" 2>/dev/null && ok "$pkg 安装完成" || warn "$pkg 安装失败（iOS 不需要可忽略）"; }
done

# ── 9. 目录 & 测试 ───────────────────────────────────────────────
step "9/9  目录初始化 & 测试"
for d in output/screenshots output/data output/reports output/logs output/mock_data output/mock_reports; do
    mkdir -p "$d"
done
ok "输出目录就绪"

python -m pytest tests/ -q --tb=short 2>/dev/null && ok "全部单元测试通过" || warn "部分测试未通过"
python tools/mock_run.py 2>/dev/null && ok "Mock 端到端测试通过" || warn "Mock 测试失败"

# ── 完成 ─────────────────────────────────────────────────────────
echo
echo "══════════════════════════════════════════════════════════"
echo "  ✅ 安装完成！"
echo
echo "  【Android / 小米手机】"
echo "    1. 小米手机开启 USB 调试（见 deploy/xiaomi_setup.md）"
echo "    2. USB 连接手机，运行:"
echo "         bash deploy/calibrate.sh --android xiaohongshu"
echo "    3. 正式运行:"
echo "         bash deploy/run.sh --platform android xiaohongshu"
echo
echo "  【iOS 手机】"
echo "    1. USB 连接 iPhone，运行:"
echo "         bash deploy/calibrate.sh xiaohongshu"
echo "    2. 正式运行:"
echo "         bash deploy/run.sh --platform ios xiaohongshu"
echo
echo "  【环境检查】"
echo "    bash deploy/check_env.sh"
echo "══════════════════════════════════════════════════════════"
echo
