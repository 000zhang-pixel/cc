# AI-Content-Hub — Claude Code 工作规范

## ⚠️ COMMIT 强提示

**每次完成以下任何一项时，必须提醒用户执行 git commit + push：**

- 修改了任何代码文件（.py / .sh / .yaml / .json）
- 修复了 bug
- 新增了功能
- 完成了一个讨论/调试环节，代码处于稳定可用状态
- 会话即将结束前

提醒语句示例：
> 这是一个重要节点，建议现在执行 commit 备份到 GitHub：
> ```bash
> cd D:/AI-Content-Hub
> git add -A
> git commit -m "描述本次改动"
> git push origin main
> ```

**不要等到用户主动问才提醒。**

---

## Python 版本要求

- **最低要求**：Python 3.9（通过 `from __future__ import annotations` 兼容 `X | Y` 联合类型注解）
- **推荐版本**：Python 3.11+（所有测试和验证脚本均在 3.11 环境开发）
- **验证命令**：统一使用 `python`，避免 `python3` 指向 3.9 导致运行失败
- **一键检查**：
  ```bash
  python --version   # 确认 >= 3.9
  cd D:/AI-Content-Hub/middleware
  python scripts/validate_handler_units.py
  python scripts/validate_scene_variety.py
  python scripts/validate_diff_strength.py
  python scripts/validate_persona_path.py
  ```

---

## 项目概览

- **路径**: `D:\AI-Content-Hub\`
- **用途**: 飞书多维表格驱动的 AI 内容生成 + 得物 ADB 自动发布系统
- **主要模块**:
  - `middleware/` — Python 中间件（Poller + Dispatcher + Handler）
  - `publish-engine/` — Bash ADB 发布引擎
  - `scripts/` — 工具脚本（飞书 Base 初始化、自动提交等）
- **GitHub**: https://github.com/000zhang-pixel/cc
- **配置文件**: `middleware/config/system.yaml`

## 自动提交

每天 23:00 由 Windows 任务计划自动运行 `scripts/auto_commit.bat`，检测改动并提交到 GitHub。

手动触发：
```bash
bash D:/AI-Content-Hub/scripts/auto_commit.sh
```
