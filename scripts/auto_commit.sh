#!/bin/bash
# =============================================================================
# 自动提交脚本 — AI-Content-Hub
# 检测本地改动，自动 commit + push 到 GitHub
# 由 Windows 任务计划每天定时触发，或手动运行
#
# 手动运行:
#   bash D:/AI-Content-Hub/scripts/auto_commit.sh
# =============================================================================

REPO_DIR="D:/AI-Content-Hub"

cd "$REPO_DIR" || { echo "[ERROR] 目录不存在: $REPO_DIR"; exit 1; }

# 检查是否有改动
if git diff --quiet && git diff --cached --quiet && [ -z "$(git status --porcelain)" ]; then
    echo "[INFO] 无改动，跳过提交"
    exit 0
fi

# 生成提交信息（带时间戳）
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
MSG="auto: 自动备份 $TIMESTAMP"

echo "[INFO] 检测到改动，开始提交..."
git add -A
git commit -m "$MSG"

echo "[INFO] 推送到 GitHub..."
git push origin main

echo "[SUCCESS] 提交完成: $MSG"
