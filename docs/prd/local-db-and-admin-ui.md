# AI-Content-Hub — 本地数据库与管理后台 PRD

**版本**: v0.1  
**日期**: 2026-04-08  
**状态**: 草稿规划中  
**关联文档**: [系统总览 PRD](ai-content-system-overview.md) · [存储设计](../storage-design.md) · [架构决策](../decisions/architecture-decisions.md)

---

## 一、背景与目标

### 1.1 现状痛点

当前系统以飞书多维表格作为唯一数据层：
- 所有状态查询依赖飞书 API 轮询（10秒/次），网络抖动时中台无法感知任务状态
- 无本地持久化：中台重启后，执行中的任务状态丢失，需手动从飞书核对
- 监控/调试只能翻飞书记录，无全局视图
- 飞书 API 有调用频率限制（每分钟约1200次），随数据量增长存在瓶颈

### 1.2 目标

**保留飞书作为人工操作入口**，新增本地层：

| 层 | 职责 | 变化 |
|----|------|------|
| 飞书多维表格 | 人工录入、配置、审核、查看内容 | 不变 |
| **本地 SQLite 数据库** | 任务状态机、执行历史、快速查询的权威数据源 | 新增 |
| **本地管理后台（Web UI）** | 无需打开飞书即可查看状态、触发操作、查看日志 | 新增 |

**不做**：不替换飞书作为内容管理 UI，不重新实现飞书的内容展示功能。

---

## 二、本地数据库 Schema 设计

### 2.1 技术选型

| 项目 | 选型 | 理由 |
|------|------|------|
| 数据库 | **SQLite**（单文件） | 零依赖，双平台直接运行，数据量级（万级记录）无需 PostgreSQL |
| ORM | **SQLAlchemy 2.x** + Alembic（迁移） | 已有 Python 栈，类型安全，迁移可版本控制 |
| 数据库文件路径 | `D:/AI-Content-Hub/data/hub.db` | `.env` 可覆盖 `LOCAL_DB_PATH` |

### 2.2 表设计总览

```
skus                ← 飞书表1 SKU信息表 镜像
plans               ← 飞书表2 内容规划表 镜像 + 本地状态扩展
prompts             ← 飞书表3 提示词生成表 镜像
contents            ← 飞书表4 内容生成表 镜像 + 本地状态扩展
publish_records     ← 飞书表5 发布执行表 镜像 + 本地状态扩展
materials           ← 飞书表6 素材知识库 镜像
tags                ← 飞书表7 标签库 镜像
task_logs           ← 本地独有：任务执行日志明细（不写飞书）
sync_cursors        ← 本地独有：飞书同步游标（增量同步用）
```

### 2.3 核心表字段

#### `skus`

```sql
CREATE TABLE skus (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feishu_record_id TEXT NOT NULL UNIQUE,   -- 飞书 record_id
    sku_code        TEXT NOT NULL UNIQUE,    -- SKU编号 MC-IP15-001
    sku_name        TEXT NOT NULL,
    spu_code        TEXT,
    product_alias   TEXT,                   -- 产品简称（用于Prompt）
    display_name    TEXT,
    category        TEXT,                   -- 手机壳/手机挂架/其他
    model           TEXT,                   -- 适配机型
    material        TEXT,                   -- JSON数组
    color           TEXT,                   -- JSON数组
    style           TEXT,                   -- JSON数组
    target_audience TEXT,                   -- JSON数组
    selling_point_1 TEXT,
    selling_point_2 TEXT,
    selling_point_3 TEXT,
    price_range     REAL,
    platforms       TEXT,                   -- JSON数组 ["得物","小红书"]
    listing_status  TEXT DEFAULT '待上架',  -- 待上架/已上架/下架
    white_bg_urls   TEXT,                   -- JSON数组，飞书附件URL列表
    synced_at       DATETIME,               -- 最后一次从飞书同步时间
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### `plans`

```sql
CREATE TABLE plans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feishu_record_id TEXT UNIQUE,           -- 飞书 record_id（同步后填入，本地创建暂为NULL）
    plan_code       TEXT NOT NULL UNIQUE,   -- T_260404_020
    sku_id          INTEGER REFERENCES skus(id),
    task_name       TEXT,
    task_type       TEXT NOT NULL,          -- AI全创作/图片实拍+AI文案/视频实拍+AI文案
    content_types   TEXT,                   -- JSON数组
    target_platforms TEXT,                  -- JSON数组
    img_count       INTEGER DEFAULT 3,
    img_per_post    INTEGER DEFAULT 4,
    video_count     INTEGER DEFAULT 0,
    video_min_sec   INTEGER,
    video_max_sec   INTEGER,
    tag_inject_n    INTEGER DEFAULT 5,
    text_model      TEXT,
    image_model     TEXT,
    video_model     TEXT,
    -- 状态机（本地权威）
    exec_status     TEXT DEFAULT '待执行',  -- 待执行/执行中/完成/失败
    confirmed_exec  BOOLEAN DEFAULT FALSE,  -- 是否已触发（防重复）
    started_at      DATETIME,
    finished_at     DATETIME,
    error_msg       TEXT,
    notes           TEXT,
    synced_at       DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### `contents`

```sql
CREATE TABLE contents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feishu_record_id TEXT UNIQUE,
    content_code    TEXT NOT NULL UNIQUE,   -- T_260404_020_img01
    plan_id         INTEGER REFERENCES plans(id),
    sku_id          INTEGER REFERENCES skus(id),
    task_type       TEXT,
    target_platform TEXT,
    content_type    TEXT,
    content_form    TEXT,                   -- 单图文/图文/视频
    title           TEXT,
    body            TEXT,
    tags            TEXT,
    local_dir       TEXT,                   -- Pending_Content/{plan_code}/{group_id}/ 绝对路径
    -- 状态机（本地权威）
    gen_status      TEXT DEFAULT '生成中',  -- 生成中/已生成/生成失败
    migrate_needed  BOOLEAN DEFAULT FALSE,
    migrate_status  TEXT,                   -- 待搬迁/搬迁中/已完成/搬迁失败
    review_status   TEXT DEFAULT '待审核',  -- 待审核/已通过/已拒绝
    review_note     TEXT,
    error_msg       TEXT,
    generated_at    DATETIME,
    synced_at       DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### `publish_records`

```sql
CREATE TABLE publish_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    feishu_record_id TEXT UNIQUE,
    pub_code        TEXT NOT NULL UNIQUE,   -- Pub_260404_020_img01
    content_id      INTEGER REFERENCES contents(id),
    publish_method  TEXT DEFAULT '待定',    -- 待定/得物自动发布/小红书手动/其他手动
    scheduled_at    DATETIME,
    -- 状态机（本地权威）
    pub_status      TEXT DEFAULT '待发布',  -- 待发布/发布中/已发布/发布失败
    published_at    DATETIME,
    post_url        TEXT,
    error_msg       TEXT,
    notes           TEXT,
    synced_at       DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### `task_logs`（本地独有，不同步飞书）

```sql
CREATE TABLE task_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,  -- plan/content/publish_record/material
    entity_id   INTEGER NOT NULL,
    entity_code TEXT,           -- 便于肉眼识别，如 T_260404_020
    level       TEXT NOT NULL,  -- INFO/WARNING/ERROR
    message     TEXT NOT NULL,
    detail      TEXT,           -- 长文本：完整错误堆栈、API响应原文
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_task_logs_entity ON task_logs(entity_type, entity_id);
CREATE INDEX idx_task_logs_created ON task_logs(created_at DESC);
```

#### `sync_cursors`

```sql
CREATE TABLE sync_cursors (
    table_name      TEXT PRIMARY KEY,       -- feishu_plan / feishu_content / …
    last_sync_at    DATETIME,               -- 最后同步时间戳（用于增量查询）
    last_page_token TEXT,                   -- 飞书分页 token（分批拉取时续用）
    sync_count      INTEGER DEFAULT 0,      -- 累计同步记录数
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2.4 索引策略

```sql
-- 高频查询场景
CREATE INDEX idx_plans_exec_status ON plans(exec_status);
CREATE INDEX idx_contents_gen_status ON contents(gen_status);
CREATE INDEX idx_contents_review_status ON contents(review_status);
CREATE INDEX idx_publish_records_pub_status ON publish_records(pub_status);
CREATE INDEX idx_contents_plan_id ON contents(plan_id);
CREATE INDEX idx_publish_records_content_id ON publish_records(content_id);
```

### 2.5 状态机约束

本地数据库是状态机的**权威数据源**。飞书侧状态变更由中台在本地更新完成后再回写。

```
plans.exec_status:
  待执行 → 执行中（触发后立即）→ 完成 / 失败

contents.gen_status:
  生成中 → 已生成 / 生成失败

contents.migrate_status:
  待搬迁 → 搬迁中 → 已完成 / 搬迁失败

contents.review_status:
  待审核 → 已通过（→ 触发创建 publish_record）/ 已拒绝

publish_records.pub_status:
  待发布 → 发布中 → 已发布 / 发布失败
```

---

## 三、后台服务架构

### 3.1 整体架构

```
┌──────────────────────────────────────────────────────┐
│                    浏览器（管理后台）                   │
│         http://localhost:8765                        │
└─────────────────────┬────────────────────────────────┘
                      │ HTTP
┌─────────────────────▼────────────────────────────────┐
│              FastAPI 后台服务（新增）                   │
│  /api/v1/*  REST API                                 │
│  /          静态文件（Vue/React 单页应用 或 Jinja2）    │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │           APIRouter 路由层                      │  │
│  │  /skus  /plans  /contents  /publish  /logs     │  │
│  └────────────────────┬───────────────────────────┘  │
│                       │                              │
│  ┌────────────────────▼───────────────────────────┐  │
│  │           Service 层                            │  │
│  │  PlanService / ContentService / PublishService  │  │
│  └────────────────────┬───────────────────────────┘  │
│                       │                              │
│  ┌────────────────────▼───────────────────────────┐  │
│  │           SQLAlchemy ORM（本地 SQLite）          │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│              现有 Middleware 进程（不改动主流程）        │
│  Poller → Dispatcher → Handlers                      │
│  ↕ 直接读写 SQLite（通过 SQLAlchemy）                  │
│  ↕ 飞书 API 双向同步                                   │
└──────────────────────────────────────────────────────┘
```

**关键决策**：FastAPI 服务与 Middleware 进程**共享同一个 SQLite 文件**，SQLite WAL 模式支持一写多读，无需消息队列。

### 3.2 FastAPI 项目结构

```
D:\AI-Content-Hub\
├── admin-server/                  ← 新增
│   ├── main.py                    ← FastAPI app 入口，挂载路由和静态文件
│   ├── routers/
│   │   ├── skus.py
│   │   ├── plans.py
│   │   ├── contents.py
│   │   ├── publish.py
│   │   └── logs.py
│   ├── services/
│   │   ├── plan_service.py
│   │   ├── content_service.py
│   │   └── publish_service.py
│   ├── schemas/                   ← Pydantic 请求/响应模型
│   ├── db.py                      ← SQLAlchemy engine + session
│   └── requirements.txt
│
├── db/                            ← 新增：数据库相关
│   ├── models.py                  ← SQLAlchemy ORM 模型（供 middleware + admin-server 共用）
│   ├── alembic/                   ← Alembic 迁移
│   │   ├── alembic.ini
│   │   └── versions/
│   └── seed.py                    ← 初始数据导入脚本
│
└── data/
    └── hub.db                     ← SQLite 数据库文件（不进 git）
```

### 3.3 REST API 设计

#### Plans

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/plans` | 列表，支持 `?status=&page=&limit=` |
| GET | `/api/v1/plans/{plan_code}` | 详情 + 关联内容列表 |
| POST | `/api/v1/plans/{plan_code}/trigger` | 手动触发执行（设 confirmed_exec=True，入 Middleware 队列） |
| POST | `/api/v1/plans/{plan_code}/retry` | 重置失败任务为待执行 |
| GET | `/api/v1/plans/{plan_code}/logs` | 该计划所有任务日志 |

#### Contents

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/contents` | 列表，支持 `?plan_code=&gen_status=&review_status=` |
| GET | `/api/v1/contents/{content_code}` | 详情 |
| POST | `/api/v1/contents/{content_code}/review` | 审核操作 `{"action": "approve"/"reject", "note": "..."}` |
| GET | `/api/v1/contents/{content_code}/files` | 列出 local_dir 下的文件（图片/视频/txt） |

#### Publish

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/publish` | 列表，支持 `?status=` |
| POST | `/api/v1/publish/{pub_code}/dispatch` | 设置发布方式 → 触发 PublishHandler |
| POST | `/api/v1/publish/{pub_code}/retry` | 重置失败记录为待发布 |

#### Logs

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/logs` | 全局日志流，支持 `?entity_type=&level=&limit=100` |
| GET | `/api/v1/logs/stream` | Server-Sent Events 实时日志推送 |

#### Sync

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/v1/sync/pull` | 手动触发从飞书全量/增量同步到本地 |
| GET | `/api/v1/sync/status` | 各表最后同步时间、记录数 |

### 3.4 启动方式

```bash
# 独立进程，与 middleware 并列运行
uvicorn admin-server.main:app --host 127.0.0.1 --port 8765 --reload
```

开机自启：在现有 `run_middleware.bat` 中追加一行，或单独创建 `run_admin.bat` + 任务计划程序任务（任务名 `AI-Content-Hub-Admin`）。

### 3.5 SQLite WAL 模式配置

```python
# db/models.py 或 db.py
from sqlalchemy import event, create_engine

engine = create_engine(
    f"sqlite:///{db_path}",
    connect_args={"check_same_thread": False},
)

@event.listens_for(engine, "connect")
def set_wal_mode(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA synchronous=NORMAL")
    dbapi_conn.execute("PRAGMA busy_timeout=5000")
```

---

## 四、飞书 → 本地数据同步方案

### 4.1 同步策略

采用**飞书为源、本地为镜像**的单向同步（写入方向：人工操作 → 飞书 → 同步到本地）。

> **例外**：中台执行过程中的状态变更（exec_status、gen_status 等）以本地为准，再回写飞书，**不走同步链路**。

### 4.2 同步时机

| 触发方式 | 场景 |
|----------|------|
| **启动时全量同步** | Middleware/Admin Server 首次启动，拉取全部飞书记录写入本地 |
| **定时增量同步** | 每 5 分钟拉取上次同步时间之后的变更（飞书 list API 支持按更新时间过滤） |
| **手动触发** | 管理后台 `/api/v1/sync/pull` 按钮，用于紧急刷新 |

### 4.3 同步器实现

```
db/sync/
├── feishu_syncer.py      ← 主入口：按表逐一同步
├── sku_syncer.py         ← 表1
├── plan_syncer.py        ← 表2
├── content_syncer.py     ← 表4（表3/5/6/7同理）
└── base_syncer.py        ← 公共逻辑：分页拉取、upsert、游标更新
```

**增量同步核心逻辑**：

```python
# base_syncer.py
def sync_table(self, table_name: str, mapper_fn, feishu_table_id: str):
    cursor = self.db.get_cursor(table_name)
    last_sync = cursor.last_sync_at or datetime(2000, 1, 1)

    page_token = None
    while True:
        records, next_token = self.feishu.list_records(
            table_id=feishu_table_id,
            filter=f"updated_at > {last_sync.timestamp()}",
            page_token=page_token,
        )
        for r in records:
            local_obj = mapper_fn(r)
            self.db.upsert(local_obj, index_col="feishu_record_id")
        
        if not next_token:
            break
        page_token = next_token
    
    self.db.update_cursor(table_name, last_sync_at=datetime.utcnow())
```

### 4.4 字段映射规则

| 场景 | 处理方式 |
|------|----------|
| 飞书多选字段 | 转为 JSON 数组字符串 `'["得物","小红书"]'` |
| 飞书附件字段 | 只同步 URL 列表，不下载实体文件 |
| 飞书关联字段 | 同步时解析出 linked record_id，映射到本地外键 |
| 飞书时间字段 | 统一转 UTC DATETIME 存储 |
| 本地状态字段 | 以本地值为准，**不从飞书覆盖**（exec_status、gen_status 等） |

### 4.5 冲突处理

```
同步时发现 feishu_record_id 已存在：
  → 对比 feishu 侧 updated_at vs 本地 synced_at
  → 若飞书更新更新：upsert 非状态字段（不覆盖 exec_status/gen_status/pub_status）
  → 若本地更新更新：跳过（本地执行期间的变更优先）
```

---

## 五、管理后台 UI 设计

### 5.1 技术选型

| 项目 | 选型 | 理由 |
|------|------|------|
| 前端框架 | **纯 Jinja2 + HTMX** | 无需 Node.js/打包工具；内部工具，交互简单；Python 全栈维护成本低 |
| CSS | TailwindCSS CDN | 无需构建，快速出样式 |
| 图表 | Chart.js CDN | 轻量，够用 |
| 备选 | Vue 3（仅在需要复杂交互时升级） | — |

### 5.2 页面结构

```
/ (Dashboard)
├── /plans              计划管理
│   └── /plans/{code}   计划详情
├── /contents           内容审核
│   └── /contents/{code} 内容详情（含图片预览）
├── /publish            发布管理
├── /logs               日志中心
└── /sync               飞书同步状态
```

### 5.3 页面详细设计

#### Dashboard（首页）

```
┌─────────────────────────────────────────────────┐
│  AI-Content-Hub  管理后台          [同步飞书] 🔄  │
├──────┬──────┬──────┬──────────────────────────  │
│ 执行中 │ 待审核 │ 待发布 │ 今日已发布                │
│  3   │  12  │  8   │   5                         │
├─────────────────────────────────────────────────┤
│  最近任务                      最近日志（ERROR）    │
│  T_260408_001 [执行中] ████░░  ❌ T_260407_009    │
│  T_260407_022 [完成]  ████████  ❌ …             │
│  …                                              │
└─────────────────────────────────────────────────┘
```

**数据卡片**（4个）：执行中任务数 / 待审核内容数 / 待发布记录数 / 今日已发布数

#### 计划管理（/plans）

列表视图，每行展示：

| 字段 | 说明 |
|------|------|
| plan_code | 可点击进详情 |
| SKU名称 | 关联SKU |
| 任务类型 | AI全创作 / 实拍类 |
| 内容组数 | img × N + vid × N |
| 状态 | 彩色 Badge |
| 开始/完成时间 | — |
| 操作 | [触发] [重试] [查看日志] |

筛选器：状态 / SKU / 日期范围

**计划详情页**：

```
T_260408_001 — 透明磨砂壳 iPhone 15 Pro    [执行中]

任务配置                    执行进度
SKU: MC-IP15-001           ████████░░ 8/10 组完成
类型: AI全创作              开始: 2026-04-08 10:23
图文: 8篇 · 视频: 2篇       耗时: 4分32秒

内容列表
┌────────────────┬──────┬──────┬──────────┬────────┐
│ 内容编号        │ 类型 │ 状态 │ 审核状态  │ 操作   │
├────────────────┼──────┼──────┼──────────┼────────┤
│ T_260408_001_img01 │ 图文 │ 已生成 │ 待审核 │ [查看] │
│ T_260408_001_img02 │ 图文 │ 生成中 │ —     │        │
└────────────────┴──────┴──────┴──────────┴────────┘

任务日志（最近20条）
[INFO]  10:23:01  开始执行任务，共10组
[INFO]  10:24:15  img01 文案生成完成
[INFO]  10:24:48  img01 图片生成完成（4张）
[ERROR] 10:27:03  img05 图片生成失败: API timeout
```

#### 内容审核（/contents）

列表视图：

| 字段 | 说明 |
|------|------|
| content_code | — |
| 标题（前30字） | — |
| 缩略图 | 第一张图 `<img>` |
| 平台 | Badge |
| 生成状态 | — |
| 审核状态 | — |
| 操作 | [查看·审核] |

**内容详情页**（重点页面）：

```
T_260408_001_img01                     [待审核]

┌─────────────────┬──────────────────────────────┐
│ 图片预览         │ 文案                          │
│ [img_01] [img_02]│ 标题：颜值爆炸！透明磨砂壳…    │
│ [img_03] [img_04]│                              │
│                 │ 正文：…（完整显示）             │
│                 │                              │
│                 │ 标签：#手机壳 #iPhone15Pro …  │
└─────────────────┴──────────────────────────────┘

            [✅ 通过]   [❌ 拒绝（填原因）]
```

点击图片可弹出大图预览。

#### 发布管理（/publish）

列表视图 + 状态 Tab（待发布 / 发布中 / 已发布 / 失败）：

| 字段 | 说明 |
|------|------|
| pub_code | — |
| 关联内容 | content_code 可跳转 |
| 平台 | — |
| 发布方式 | 下拉选择（同飞书字段）|
| 状态 | — |
| 实际发布时间 | — |
| 帖子链接 | 可点击外跳 |
| 操作 | [发布] [重试] |

[发布] 按钮 → 弹出确认框 → POST `/api/v1/publish/{pub_code}/dispatch`

#### 日志中心（/logs）

```
筛选：[全部 ▼] [ERROR ▼] [实体类型 ▼]          [实时刷新 ●]

时间            级别    实体            消息
10:27:03       ERROR   T_260408_001_img05  图片生成失败: API timeout
                        详情 ▼（点击展开完整堆栈）
10:24:48       INFO    T_260408_001_img01  图片生成完成（4张）
```

实时日志通过 SSE（`/api/v1/logs/stream`）推送，无需手动刷新。

#### 飞书同步（/sync）

```
飞书同步状态                           [手动全量同步]

表名            记录数    最后同步        状态
SKU信息表        24      10:15:03        ✅ 正常
内容规划表       156     10:15:04        ✅ 正常
内容生成表       892     10:15:06        ✅ 正常
发布执行表       634     10:15:07        ✅ 正常
```

---

## 六、中台改造要点

### 6.1 Middleware 改动范围

**新增**（不改动现有 Handler 主流程）：

1. 启动时初始化 SQLAlchemy ORM，WAL 模式开启
2. 启动时执行全量飞书同步（`FeishuSyncer.sync_all()`）
3. 后台启动增量同步定时器（每5分钟）
4. 各 Handler 执行状态变更时，**先写本地 DB，再回写飞书**
5. `task_logs` 写入封装为公共函数 `log_task(entity_type, entity_id, level, message, detail=None)`

**不改动**：
- Poller 轮询逻辑（继续监听飞书触发字段）
- Handler 核心业务逻辑
- 飞书 API 调用层

### 6.2 状态写入顺序（Handler 标准流程）

```python
# 标准模式：本地优先，飞书兜底
async def handle(self, task: Task):
    # 1. 本地状态先行
    db.update(plans, plan_code=task.plan_code, exec_status="执行中")
    log_task("plan", plan.id, "INFO", "开始执行任务")
    
    try:
        # 2. 业务执行
        result = await self._generate_content(task)
        
        # 3. 本地写入成功结果
        db.update(contents, content_code=..., gen_status="已生成")
        log_task("content", content.id, "INFO", "生成完成")
        
        # 4. 回写飞书（允许失败，不影响本地状态）
        await feishu.update_record(..., {"生成状态": "已生成"})
        
    except Exception as e:
        # 5. 本地写入失败状态
        db.update(plans, exec_status="失败", error_msg=str(e))
        log_task("plan", plan.id, "ERROR", "执行失败", detail=traceback.format_exc())
        
        # 6. 回写飞书失败状态
        await feishu.update_record(..., {"执行状态": "失败"})
```

---

## 七、实施阶段规划

| 阶段 | 内容 | 产出 |
|------|------|------|
| **P0** | 数据库 Schema 落地：建 `db/models.py`，Alembic init，创建 `hub.db` | ORM 可用 |
| **P1** | 飞书同步器：`FeishuSyncer` + 增量同步定时器，Middleware 启动时触发 | 本地数据实时镜像 |
| **P2** | Middleware Handler 改造：状态变更写本地 DB + task_logs | 本地状态权威 |
| **P3** | FastAPI Admin Server：API + Dashboard + Plans + Logs 页面 | 基础管理后台可用 |
| **P4** | 内容审核页面：图片预览 + 一键审核按钮 | 免打开飞书审核 |
| **P5** | 发布管理页面 + SSE 实时日志流 | 全功能后台 |

---

## 八、非功能需求

| 项目 | 要求 |
|------|------|
| 性能 | 列表页 < 200ms（SQLite索引保证），图片预览本地文件直接 serve |
| 可用性 | Admin Server 崩溃不影响 Middleware（独立进程） |
| 安全 | 仅 127.0.0.1 监听，不对外网暴露；无需认证（本机工具） |
| 跨平台 | Windows + Mac 均可运行（SQLite + Python 全栈无平台依赖） |
| 数据安全 | `data/hub.db` 加入 `.gitignore`；定期备份脚本 TBD |

---

*文档状态：草稿 — 待用户审阅后进入 P0 实施*
