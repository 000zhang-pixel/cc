#!/bin/bash
# =============================================================================
# 得物发布系统 - V4.2 (反检测增强版，跨平台 Windows/Mac)
#
# V4.2 变更（2026-04-06）:
#   - 替换 monkey 启动为 am start（消除最高风险检测特征）
#   - 所有固定 sleep 改为 rand_sleep 随机范围（破坏时序规律性）
#   - tap 改为 tap_jitter 带坐标抖动（模拟真实触摸偏差）
#   - 批量任务间隔由固定5s改为3~6分钟随机
#   - 新增 is_publishable_hour 发布时段控制（仅9-22点运行）
#   - 跨平台支持（Windows Git Bash / macOS）
#
# 调用方式（由 Python 中间件触发）:
#   CONTENT_WORKSPACE_DIR=D:/AI-Content-Hub/content-store/Pending_Content/PLAN/img01 \
#   bash publish_engine_v40.sh single <pub_id> <content_id>
#
# Workspace 文件布局:
#   {CONTENT_WORKSPACE_DIR}/
#     title.txt          ← 标题
#     body_tags.txt      ← 正文+标签（合并文件）
#     img_01.jpg ~ img_N.jpg  ← 图片（最多10张）
#
# 设备基准: Redmi K30 (1080x2400)，已在 2026-04-06 校验全部坐标
# =============================================================================

set -e

# ─── 平台检测 ────────────────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"
case "$OS_TYPE" in
    Darwin*)  PLATFORM="mac" ;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
    *)        PLATFORM="linux" ;;
esac

# 确保 adb 可用
if [ "$PLATFORM" = "windows" ]; then
    export PATH="$PATH:/c/platform-tools"
elif [ "$PLATFORM" = "mac" ]; then
    # Homebrew 或 Android SDK 路径
    if [ -d "$HOME/Library/Android/sdk/platform-tools" ]; then
        export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools"
    elif [ -d "/opt/homebrew/bin" ]; then
        export PATH="$PATH:/opt/homebrew/bin"
    fi
fi

# adb 命令封装：Windows Git Bash 需要 MSYS_NO_PATHCONV=1 防止路径被转换
_adb() {
    if [ "$PLATFORM" = "windows" ]; then
        MSYS_NO_PATHCONV=1 adb "$@"
    else
        adb "$@"
    fi
}

# ─── 坐标配置（Redmi K30 1080x2400）─────────────────────────────────────────
COORD_CAMERA="995 155"         # 首页右上角相机图标（发布入口）
COORD_IMG_01="312 560"         # 图片选择格 01（已验证 2026-04-05）
COORD_IMG_02="675 560"         # 图片选择格 02（已验证 2026-04-05）
COORD_IMG_03="1040 560"        # 图片选择格 03（已验证 2026-04-05）
COORD_IMG_04="312 930"         # 图片选择格 04（已验证 2026-04-05）
COORD_IMG_05="675 930"         # 图片选择格 05（已验证 2026-04-05）
COORD_IMG_06="1040 930"        # 图片选择格 06（已验证 2026-04-06）
COORD_IMG_07="312 1290"        # 图片选择格 07（已验证 2026-04-06）
COORD_IMG_08="675 1290"        # 图片选择格 08（已验证 2026-04-06）
COORD_IMG_09="1040 1290"       # 图片选择格 09（已验证 2026-04-06）
COORD_IMG_10="312 1650"        # 图片选择格 10（已验证 2026-04-06）
COORD_NEXT="935 2150"          # 下一步按钮
COORD_TITLE="250 550"          # 标题输入框
COORD_CONTENT="250 580"        # 正文输入框
COORD_KEYBOARD_HIDE="995 1570" # 收起键盘（已验证 2026-04-06）
COORD_SAVE_DRAFT="95 2160"     # 存草稿按钮（左下角，已验证 2026-04-05）
COORD_SAVE_EXIT="530 2000"     # 保存并退出按钮（已验证 2026-04-05）
COORD_CLIPBOARD="500 1590"     # 微信输入法剪贴板按钮
COORD_POPUP_ABANDON="375 1480" # 弹窗「是否继续编辑」- 放弃按钮（已验证 2026-04-06，bounds [224,1423][526,1538]）

PHONE_ALBUM_DIR="/sdcard/DCIM/Camera"
DEWU_PACKAGE="com.shizhuang.duapp"
DEWU_MAIN_ACTIVITY="com.shizhuang.duapp.modules.home.ui.SplashActivity"

# ─── 日志 ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }

# ─── 随机等待（破坏固定时序特征）──────────────────────────────────────────────
# 用法: rand_sleep <min秒> <max秒>（支持小数）
rand_sleep() {
    local min=$1 max=$2
    local delay
    delay=$(awk -v min="$min" -v max="$max" -v seed="$RANDOM" \
        'BEGIN { srand(seed); printf "%.1f", min + rand() * (max - min) }')
    sleep "$delay"
}

# ─── 带坐标抖动的 tap（模拟真实手指偏差）────────────────────────────────────
# 用法: tap_jitter "<x> <y>" [抖动像素=8] [等待秒max=1.5]
tap_jitter() {
    local coord="$1" jitter="${2:-8}" max_wait="${3:-1.5}"
    local x y dx dy
    x=$(echo "$coord" | awk '{print $1}')
    y=$(echo "$coord" | awk '{print $2}')
    dx=$(awk -v j="$jitter" -v s="$RANDOM" 'BEGIN{srand(s); printf "%d", int((rand()*2-1)*j)}')
    dy=$(awk -v j="$jitter" -v s="$RANDOM" 'BEGIN{srand(s); printf "%d", int((rand()*2-1)*j)}')
    _adb shell input tap $((x+dx)) $((y+dy)) > /dev/null 2>&1
    rand_sleep 0.3 "$max_wait"
}

# 保留原 tap 接口作为兼容别名（内部改用 tap_jitter）
tap() {
    tap_jitter "$1" 6 "${2:-1.0}"
}

# ─── 发布时段控制（仅在合理时段发布）────────────────────────────────────────
# 返回 0 = 可发布，1 = 非时段
is_publishable_hour() {
    local hour
    hour=$(date +%H)
    # 允许时段: 9-12, 14-22（模拟人工操作时间）
    if [ "$hour" -ge 9 ] && [ "$hour" -le 12 ]; then return 0; fi
    if [ "$hour" -ge 14 ] && [ "$hour" -le 22 ]; then return 0; fi
    return 1
}

# ─── 剪贴板输入（跨平台）───────────────────────────────────────────────────
win_copy_file_to_clipboard() {
    local file="$1"
    log_info "复制到剪贴板: $file"
    if [ "$PLATFORM" = "mac" ]; then
        cat "$file" | pbcopy 2>/dev/null
    else
        powershell.exe -Command "Get-Content -LiteralPath '$file' -Encoding UTF8 -Raw | Set-Clipboard" 2>/dev/null
    fi
    rand_sleep 1.2 2.5   # 等待微信输入法同步
}

# ─── 相册管理 ────────────────────────────────────────────────────────────────
clear_album() {
    log_info "清空手机相册..."
    adb shell "rm -rf $PHONE_ALBUM_DIR/*" > /dev/null 2>&1 || true
    adb shell "rm -rf /sdcard/DCIM/.thumbnails/*" > /dev/null 2>&1 || true
    rand_sleep 0.8 1.5
    log_success "相册已清空"
}

copy_images_to_phone() {
    local source_dir="$1"
    local copy_count=0 total=0
    log_info "推送图片到手机..."
    for i in 01 02 03 04 05 06 07 08 09 10; do
        local img="$source_dir/img_$i.jpg"
        [ -f "$img" ] || continue
        total=$((total + 1))
        local push_output
        push_output=$(_adb push "$img" "$PHONE_ALBUM_DIR/${i}.jpg" 2>&1)
        if [ $? -eq 0 ]; then
            log_info "  ✅ img_$i.jpg"
            copy_count=$((copy_count + 1))
        else
            log_error "  ❌ img_$i.jpg push失败: $push_output"
        fi
    done
    log_info "推送完成: $copy_count/$total"
    [ "$copy_count" -eq 0 ] && return 1
    return 0
}

refresh_album() {
    log_info "刷新手机相册..."
    _adb shell am broadcast \
        -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \
        -d file:///sdcard/DCIM/ > /dev/null 2>&1
    sleep 3
}

# ─── 弹窗处理（首页「是否继续编辑」，仅异常中断后才出现）───────────────────
# 检测方式：uiautomator dump UI 层次树，grep 关键词
# 此函数 best-effort：超时/失败均跳过，不影响主流程
check_and_close_popup() {
    log_info "检测首页弹窗..."
    local tmp_xml="/tmp/ui_dump_$$.xml"
    local dump_ok=0

    if [ "$PLATFORM" = "windows" ]; then
        # Windows: 用 PowerShell 实现 12s 超时（防止 adb.exe 挂住）
        local ps_result
        ps_result=$(powershell.exe -NoProfile -Command "\$psi = New-Object System.Diagnostics.ProcessStartInfo; \$psi.FileName = 'C:\platform-tools\adb.exe'; \$psi.Arguments = 'shell uiautomator dump /sdcard/ui_dump.xml'; \$psi.UseShellExecute = \$false; \$psi.RedirectStandardOutput = \$true; \$psi.RedirectStandardError = \$true; \$p = [System.Diagnostics.Process]::Start(\$psi); if (-not \$p) { Write-Output 'fail:no_process'; return }; if (-not \$p.WaitForExit(12000)) { try { \$p.Kill() } catch {}; Write-Output 'fail:timeout' } else { Write-Output ('ok:' + \$p.ExitCode) }" 2>/dev/null)
        [ "${ps_result}" = "ok:0" ] && dump_ok=1
    else
        # Mac/Linux: 用系统 timeout 命令
        if timeout 12 adb shell uiautomator dump /sdcard/ui_dump.xml > /dev/null 2>&1; then
            dump_ok=1
        fi
    fi

    if [ "$dump_ok" -ne 1 ]; then
        log_warn "UI dump 超时或失败，继续发布"
        return 0
    fi

    _adb pull /sdcard/ui_dump.xml "$tmp_xml" > /dev/null 2>&1 || true
    _adb shell rm /sdcard/ui_dump.xml > /dev/null 2>&1 || true

    if grep -q '是否继续编辑' "$tmp_xml" 2>/dev/null; then
        log_info "检测到弹窗（是否继续编辑），点击放弃..."
        _adb shell input tap $COORD_POPUP_ABANDON > /dev/null 2>&1
        rand_sleep 2.5 4   # 弹窗关闭后等首页完全稳定，再继续
        log_success "弹窗已关闭"
    else
        log_info "无弹窗，继续"
    fi

    rm -f "$tmp_xml" 2>/dev/null || true
    return 0
}

# ─── 核心发布流程 ─────────────────────────────────────────────────────────────
publish_single_v40() {
    local content_id="$1"
    local pub_id="$2"

    log_info "========================================="
    log_info "开始发布: $content_id (任务: $pub_id)"
    log_info "========================================="

    # —— 读取素材 ——
    local source_dir title body_content
    source_dir="$CONTENT_WORKSPACE_DIR"
    [ -z "$source_dir" ] && { log_error "未设置 CONTENT_WORKSPACE_DIR"; return 1; }
    [ ! -d "$source_dir" ] && { log_error "workspace目录不存在: $source_dir"; return 1; }

    title=$(cat "$source_dir/title.txt" 2>/dev/null || echo "")
    body_content=$(cat "$source_dir/body_tags.txt" 2>/dev/null || echo "")

    if [ -z "$title" ] || [ -z "$body_content" ]; then
        log_error "标题或正文为空 (title=${#title}字 body=${#body_content}字)"
        return 1
    fi
    log_info "标题: ${title:0:60}"
    log_info "正文: ${body_content:0:80}..."

    # —— 步骤0: 相册准备 ——
    log_info "--- 步骤0: 准备图片 ---"
    clear_album
    copy_images_to_phone "$source_dir" || { log_error "图片推送失败，中止发布"; return 1; }
    refresh_album   # 推完图立即刷新媒体库，确保选择器里只有本次图片

    # —— 步骤1: 启动得物App（用 am start 替代 monkey，消除自动化标记）——
    log_info "--- 步骤1: 启动得物App ---"
    # 先回到桌面，确保干净起点
    _adb shell input keyevent 3 > /dev/null 2>&1
    rand_sleep 1 1.5
    # 无论是否在运行都强制关闭
    _adb shell am force-stop "$DEWU_PACKAGE" > /dev/null 2>&1
    rand_sleep 1.5 3
    # 启动得物，捕获输出以便排查
    local start_output
    start_output=$(_adb shell am start -n "${DEWU_PACKAGE}/${DEWU_MAIN_ACTIVITY}" --user 0 2>&1)
    log_info "am start 输出: $start_output"
    if echo "$start_output" | grep -qiE "error|exception|not found|unable"; then
        log_error "得物启动失败: $start_output"
        return 1
    fi
    log_info "等待App加载..."
    rand_sleep 6 11
    check_and_close_popup || true   # best-effort，弹窗检测失败不中断发布
    rand_sleep 0.8 1.5

    # —— 步骤2: 点击相机图标（发布入口）——
    log_info "--- 步骤2: 点击相机图标 ($COORD_CAMERA) ---"
    tap_jitter "$COORD_CAMERA" 8 2.5

    # —— 步骤3: 动态选择图片（数量 = workspace 实际图片数，最多10张）——
    local img_count
    img_count=$(ls "$source_dir"/img_*.jpg 2>/dev/null | wc -l)
    log_info "--- 步骤4: 选择图片 (共 $img_count 张) ---"
    local img_coords=("$COORD_IMG_01" "$COORD_IMG_02" "$COORD_IMG_03" "$COORD_IMG_04" "$COORD_IMG_05"
                      "$COORD_IMG_06" "$COORD_IMG_07" "$COORD_IMG_08" "$COORD_IMG_09" "$COORD_IMG_10")
    for (( idx=0; idx<img_count && idx<10; idx++ )); do
        tap_jitter "${img_coords[$idx]}" 6 1.2
    done

    # —— 步骤5: 下一步（图片编辑页）——
    log_info "--- 步骤5: 下一步（图片编辑）---"
    tap_jitter "$COORD_NEXT" 8 3.5

    # —— 步骤6: 下一步（文字编辑页）——
    log_info "--- 步骤6: 下一步（文字编辑）---"
    tap_jitter "$COORD_NEXT" 8 3.5

    # —— 步骤7: 输入标题 ——
    log_info "--- 步骤7: 输入标题 ---"
    win_copy_file_to_clipboard "$source_dir/title.txt"
    tap_jitter "$COORD_TITLE" 10 1.2    # 点击标题框
    tap_jitter "$COORD_CLIPBOARD" 6 1   # 点击微信输入法剪贴板粘贴

    # —— 步骤7: 输入正文和标签 ——
    log_info "--- 步骤7: 输入正文和标签 ---"
    win_copy_file_to_clipboard "$source_dir/body_tags.txt"
    tap_jitter "$COORD_CONTENT" 10 1.2  # 点击正文框
    tap_jitter "$COORD_CLIPBOARD" 6 1   # 点击微信输入法剪贴板粘贴

    # —— 步骤7.5: 收起键盘（输入法遮挡草稿按钮，用返回键关闭，不依赖坐标）——
    log_info "--- 步骤7.5: 收起键盘 (keyevent BACK) ---"
    _adb shell input keyevent 4 > /dev/null 2>&1   # BACK 键收起输入法
    rand_sleep 0.8 1.5

    # —— 步骤8: 存草稿 ——
    log_info "--- 步骤8: 存草稿 ($COORD_SAVE_DRAFT) ---"
    tap_jitter "$COORD_SAVE_DRAFT" 8 2.5

    # —— 步骤9: 保存并退出（回到首页）——
    log_info "--- 步骤9: 保存并退出 ($COORD_SAVE_EXIT) ---"
    tap_jitter "$COORD_SAVE_EXIT" 8 2.5

    log_success "========================================="
    log_success "发布完成: $content_id"
    log_success "========================================="
    return 0
}

# ─── 批量发布 ─────────────────────────────────────────────────────────────────
# 遍历 parent_dir 下所有子目录，每个子目录作为一个 workspace 依次发布
# 用法: bash publish_engine_v40.sh batch "D:/AI-Content-Hub/content-store/Pending_Content/T_260404_020"
publish_batch() {
    local parent_dir="$1"
    [ -z "$parent_dir" ] && { log_error "用法: $0 batch <workspace_parent_dir>"; return 1; }
    [ ! -d "$parent_dir" ] && { log_error "目录不存在: $parent_dir"; return 1; }

    local success=0 fail=0 total=0

    for group_dir in "$parent_dir"/*/; do
        [ -d "$group_dir" ] || continue
        local group_id
        group_id=$(basename "$group_dir")
        total=$((total + 1))

        log_info "===== 批量任务 [$total] $group_id ====="
        if CONTENT_WORKSPACE_DIR="$group_dir" publish_single_v40 "$group_id" "batch_${total}"; then
            success=$((success + 1))
            log_success "[$total] $group_id 完成"
        else
            fail=$((fail + 1))
            log_error "[$total] $group_id 失败，继续下一个"
        fi

        # 任务间隔：3~6分钟随机等待，模拟人工操作节奏
        if [ -d "$group_dir" ]; then
            local wait_sec
            wait_sec=$(awk 'BEGIN{srand(); printf "%d", 180 + rand()*180}')
            log_info "===== 任务间等待 ${wait_sec}s（防频率检测）====="
            sleep "$wait_sec"
        fi
    done

    log_info "===== 批量完成: 成功 $success / 失败 $fail / 共 $total ====="
    [ "$fail" -gt 0 ] && return 1
    return 0
}

# ─── 入口 ────────────────────────────────────────────────────────────────────
show_help() {
    echo "得物发布系统 V4.2 (跨平台 Windows/Mac ADB版)"
    echo "用法:"
    echo "  $0 single <pub_id> <content_id>       # 单次发布（Python中间件调用）"
    echo "  $0 batch  <workspace_parent_dir>       # 批量发布（手动触发）"
    echo ""
    echo "必填环境变量: CONTENT_WORKSPACE_DIR=D:/AI-Content-Hub/content-store/Pending_Content/PLAN/GROUP"
}

main() {
    case "$1" in
        single)
            [ -z "$2" ] || [ -z "$3" ] && { echo "用法: $0 single <pub_id> <content_id>"; exit 1; }
            publish_single_v40 "$3" "$2"
            ;;
        batch)
            [ -z "$2" ] && { echo "用法: $0 batch <workspace_parent_dir>"; exit 1; }
            publish_batch "$2"
            ;;
        -h|--help|help) show_help ;;
        *) echo "未知命令: $1"; show_help; exit 1 ;;
    esac
}

main "$@"
