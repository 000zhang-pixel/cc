#!/bin/bash
# 一键引导脚本：拉代码 + 全自动部署
# Mac 终端运行:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/000zhang-pixel/cc/claude/appium-screenshot-automation-1QqRx/appium-screenshot-system/deploy/bootstrap.sh)"

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✔]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
err()  { echo -e "${RED}[✘]${NC} $1"; exit 1; }
info() { echo -e "${BLUE}[→]${NC} $1"; }

echo
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Appium 截图 & 舆情系统 —— 一键引导安装                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo

REPO_URL="https://github.com/000zhang-pixel/cc.git"
BRANCH="claude/appium-screenshot-automation-1QqRx"
INSTALL_DIR="$HOME/appium-screenshot-system"

# ── 1. 检查 git ─────────────────────────────────────────────────
info "检查 git..."
command -v git &>/dev/null || err "git 未安装，请先安装 Xcode Command Line Tools: xcode-select --install"
ok "git $(git --version | awk '{print $3}')"

# ── 2. 克隆或更新代码 ────────────────────────────────────────────
echo
if [ -d "$INSTALL_DIR/.git" ]; then
    info "目录已存在，更新代码..."
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" checkout "$BRANCH"
    git -C "$INSTALL_DIR" pull origin "$BRANCH"
    ok "代码已更新到最新"
else
    info "克隆代码到 $INSTALL_DIR ..."
    # 只克隆指定分支，速度更快
    git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$HOME/cc-repo" 2>/dev/null || \
        git clone "$REPO_URL" "$HOME/cc-repo"
    # 把子目录移到目标位置
    cp -r "$HOME/cc-repo/appium-screenshot-system" "$INSTALL_DIR"
    rm -rf "$HOME/cc-repo"
    ok "代码已克隆到 $INSTALL_DIR"
fi

# ── 3. 进入目录并运行安装脚本 ────────────────────────────────────
echo
info "进入项目目录: $INSTALL_DIR"
cd "$INSTALL_DIR"

info "运行完整安装程序..."
bash deploy/install.sh

# ── 4. 完成提示 ──────────────────────────────────────────────────
echo
echo "══════════════════════════════════════════════════════════"
echo "  项目已安装到: $INSTALL_DIR"
echo
echo "  后续所有操作都在这个目录下进行:"
echo "    cd $INSTALL_DIR"
echo
echo "  连上小米手机后运行:"
echo "    bash deploy/calibrate.sh --android xiaohongshu"
echo "══════════════════════════════════════════════════════════"
echo
