# Phase 1 完成归档：本地数据库 + 管理后台

**归档日期**：2026-04-09  
**状态**：✅ 全部完成

---

## 已完成模块清单

### P0 — 本地数据库层
| 文件 | 说明 |
|------|------|
| `db/models.py` | SQLAlchemy 2.x ORM，10张表，WAL 模式 |
| `db/repo.py` | 仓库层：plan/content/publish_record 状态变更 + TaskLog 写入 |
| `db/__init__.py` | 统一导出所有公开函数 |
| `db/alembic/env.py` | Alembic 迁移配置 |
| `db/alembic/versions/75291048e26c_initial_schema.py` | 初始 Schema 迁移（全量建表） |
| `data/hub.db` | SQLite 数据库文件（WAL，不进 git） |

**数据库表**：`skus`, `plans`, `prompts`, `contents`, `publish_records`, `materials`, `tags`, `task_logs`, `sync_cursors`

### P1 — 飞书增量同步
| 文件 | 说明 |
|------|------|
| `db/sync/syncer.py` | FeishuSyncer：增量同步 plan/content/publish 等核心表 |
| `middleware/main.py` | 启动时触发全量同步 + 每5分钟定时增量同步 |

### P2 — Handler 状态写入本地 DB
所有5个 Handler 在状态变更时同步写入本地 DB：

| Handler | 写入内容 |
|---------|----------|
| `content_generation.py` | mark_plan_started/done/failed，upsert_content，update_content_status |
| `material_migration.py` | update_content_status（migrate_status），log_exc |
| `publish.py` | update_publish_status（已发布/发布失败），log_task |
| `material_analysis.py` | log_task，log_exc |
| `publish_record_creator.py` | upsert_publish_record，log_task |

### P3 — FastAPI 管理后台
| 文件 | 说明 |
|------|------|
| `admin-server/main.py` | FastAPI 入口，8765 端口，18条路由 |
| `admin-server/routers/plans.py` | 规划任务 CRUD + retry |
| `admin-server/routers/contents.py` | 内容管理 + 审核 + 文件列表 |
| `admin-server/routers/publish.py` | 发布记录 + retry |
| `admin-server/routers/logs.py` | 任务日志分页 + SSE 实时流 |
| `admin-server/routers/sync.py` | 手动触发同步 + 同步状态 |
| `admin-server/schemas/__init__.py` | Pydantic v2 响应模型 |
| `admin-server/templates/index.html` | 管理 UI（HTMX + TailwindCSS CDN） |
| `admin-server/requirements.txt` | fastapi, uvicorn, pydantic, sqlalchemy |

### P4 — 内容审核页面
集成在 `index.html` 内容 Tab：approve/reject 按钮，状态筛选器。

### P5 — 发布管理 + SSE 实时日志流
- `GET /api/v1/logs/stream`：SSE 推流，每2秒轮询新 TaskLog
- 前端日志 Tab 支持开启/关闭实时流

### 自启动配置
| 文件 | 说明 |
|------|------|
| `middleware/_launcher.vbs` | 静默启动 middleware（无控制台窗口） |
| `admin-server/_launcher.vbs` | 静默启动 admin-server |
| `admin-server/run_admin.bat` | 手动启动脚本 |
| Windows 计划任务 `AI-Content-Hub-Middleware` | 登录触发，RunLevel Highest |
| Windows 计划任务 `AI-Content-Hub-Admin` | 登录触发，RunLevel Highest |

---

## 关键架构决策

1. **SQLite WAL 模式**：middleware 写、admin-server 读，不冲突
2. **状态机以本地 DB 为准**：不从飞书同步覆盖 status 字段
3. **Admin Server 仅 127.0.0.1**：无需认证
4. **Alembic 已初始化**：revision `75291048e26c` 为初始全量建表（待 Phase 2 切换启动方式）

---

## Phase 2 待实施项（见 phase-2-ops-enhancements.md）

- Alembic 迁移管理接管 create_all
- 日志文件轮转（RotatingFileHandler）
- 管理后台数据看板（/api/v1/stats）
- 审核流程闭环（approve → 自动创建发布记录）
