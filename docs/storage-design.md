# AI-Content-Hub 本地存储结构设计

**版本**: v2.0  
**确认日期**: 2026-04-07  
**状态**: 生产使用（Windows + Mac 双平台）

---

## 目录结构

```
{LOCAL_STORAGE_ROOT}/
├── inbox/                         ← 原始素材输入区（用户手动放入）
│   └── {sku_code}_{date}/         ← 例: SKU002_20260404
│       └── {batch}/               ← 例: post01, post02
│           ├── DSC001.jpg
│           └── DSC002.jpg
│
├── Pending_Content/               ← 生成内容工作区（系统读写，发布引擎读取）
│   └── {plan_code}/               ← 例: T_260404_020
│       ├── plan.json
│       ├── img01/                 ← 图文帖
│       │   ├── content.json       ← 元数据 + 状态追踪
│       │   ├── title.txt          ← 发布引擎直接读取
│       │   ├── body_tags.txt      ← 发布引擎直接读取
│       │   └── img_01.jpg … img_N.jpg
│       └── vid01/                 ← 视频帖
│           ├── content.json
│           ├── title.txt
│           ├── body_tags.txt
│           └── video.mp4
│
└── archive/                       ← 发布归档区（发布成功后自动移入）
    └── {year_month}/              ← 例: 2026-04
        └── {plan_code}/{group_id}/
```

---

## 平台路径配置

| 平台 | LOCAL_STORAGE_ROOT |
|------|--------------------|
| Windows | `D:/AI-Content-Hub/content-store` |
| Mac | `~/openclaw/workspace/content-store` |

路径通过 `.env` 文件中的 `LOCAL_STORAGE_ROOT` 配置，代码无平台判断逻辑。

---

## 三区职责边界

| 区域 | 写入方 | 读取方 | 清理方 |
|------|--------|--------|--------|
| `inbox/` | 用户手动 | MaterialMigrationHandler（拷贝） | 用户手动 |
| `Pending_Content/` | ContentGenerationHandler / MaterialMigrationHandler | PublishHandler → publish_engine.sh | `archive_content()` 发布成功后自动移走 |
| `archive/` | `archive_content()` | 人工查阅 | 定期人工清理 |

---

## 状态流转（content.json status 字段）

```
generated → review_passed → queued → published → [自动归档到 archive/]
                                   ↘ publish_failed   （Pending_Content 保留，可重试）
```

---

## 发布引擎接口约定

```bash
CONTENT_WORKSPACE_DIR=D:/AI-Content-Hub/content-store/Pending_Content/T_260404_020/img01 \
  bash publish_engine_v40.sh single <pub_id> <content_id>
```

脚本从 `$CONTENT_WORKSPACE_DIR` 直接读取：
- `title.txt` → PowerShell 复制到剪贴板 → 粘贴到 App
- `body_tags.txt` → 同上
- `img_01.jpg` … → `adb push` 到手机相册

**路径格式**: 正斜杠 `D:/AI-Content-Hub/...`（adb 兼容）

---

## 跨平台同步方案

见 [sync-setup.md](sync-setup.md)
