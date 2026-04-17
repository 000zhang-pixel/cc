# AI-Content-Hub 系统设计与使用文档

> 版本：2026-04-17 | 适用分支：main

---

## 目录

1. [系统概述](#1-系统概述)
2. [整体架构](#2-整体架构)
3. [飞书多维表格结构](#3-飞书多维表格结构)
4. [任务类型与触发机制](#4-任务类型与触发机制)
5. [内容生成全流程](#5-内容生成全流程)
6. [提示词构建详解](#6-提示词构建详解)
7. [AI 模型适配器](#7-ai-模型适配器)
8. [本地存储与数据库](#8-本地存储与数据库)
9. [发布流程](#9-发布流程)
10. [素材搬迁与分析](#10-素材搬迁与分析)
11. [配置参考](#11-配置参考)
12. [运维操作手册](#12-运维操作手册)

---

## 1. 系统概述

AI-Content-Hub 是一套以**飞书多维表格为控制面板**、**Python middleware 为执行引擎**的自动化内容生产与发布系统，用于驱动得物、小红书等平台的种草内容批量生产。

**核心能力：**
- 从飞书规划表触发，自动完成"SKU 信息 → 场景分配 → Prompt 构建 → 文案/图片/视频生成 → 结果回写飞书 + 本地存档"的全链路
- 支持多种任务类型：纯 AI 全创作、图片实拍配 AI 文案、视频实拍配 AI 文案
- 多模型支持（DeepSeek / GPT / Kimi 写文案，Nanobanana-Gemini / 火山引擎 生图，火山引擎 Seedance 生视频）
- 内置差异化机制：同一任务多组内容强制不同标题句式和叙事角度
- 内置一致性约束：同一组多张图片保持同一人物外貌/服装/发型

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                  飞书多维表格（云端）                      │
│  表1-SKU  表2-规划  表3-Prompt  表4-内容  表5-发布        │
│  表6-素材  表7-标签  表8-策略   表9-ShotPlan  表10-场景   │
└────────────────────────┬─────────────────────────────────┘
                         │ 双向读写（lark-oapi SDK）
                         ▼
┌──────────────────────────────────────────────────────────┐
│                    Middleware（本地进程）                  │
│                                                          │
│  ┌──────────┐    ┌──────────────┐   ┌────────────────┐  │
│  │  Poller  │───▶│  Task Queue  │──▶│   Dispatcher   │  │
│  │ (10s轮询)│    │  (内存队列)   │   │  (4 workers)   │  │
│  └──────────┘    └──────────────┘   └───────┬────────┘  │
│                                             │            │
│          ┌──────────────┬─────────────┬─────┴──────┐    │
│          ▼              ▼             ▼            ▼    │
│  ContentGeneration  MaterialMig  PublishRecord  Publish  │
│  Handler            Handler      Creator        Handler  │
│          │                                      │        │
│          ▼                                      ▼        │
│  ┌────────────────┐                   ┌──────────────┐  │
│  │  AI Adapters   │                   │ 得物/小红书   │  │
│  │ Text/Img/Video │                   │  发布引擎     │  │
│  └────────────────┘                   └──────────────┘  │
│          │                                               │
│          ▼                                               │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Local Storage (Pending_Content/{plan}/{group}/)   │  │
│  │  SQLite DB (hub.db) — 飞书镜像 + 状态机            │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**进程组成：**

| 组件 | 线程 | 职责 |
|------|------|------|
| Poller | 独立 daemon 线程 | 每 10 秒轮询飞书 5 张表，发现触发条件时即刻锁定记录、入队 |
| Dispatcher | 4 个 worker 线程 | 从队列取 Task，路由到对应 Handler 串行执行 |
| FeishuSyncer | 独立 daemon 线程 | 每 5 分钟增量同步飞书数据到本地 SQLite |

---

## 3. 飞书多维表格结构

系统使用 11 张飞书表，均在同一个 Base（多维表格文档）下。

### 表1 — SKU 产品表 (`sku`)

存储商品基础信息，是整个系统的数据源头。

| 字段 | 类型 | 说明 |
|------|------|------|
| SKU编号 | 文本 | 唯一标识，如 `SJL0413001` |
| SKU名称 | 文本 | 完整商品名 |
| 产品简称 | 文本 | Prompt 中的简短称呼 |
| 品类 | 单选 | 手机配件/手机壳/其他，用于策略匹配 |
| 颜色/材质/风格 | 多选 | 注入图片 Prompt 的产品描述 |
| 目标人群 | 多选 | |
| 卖点1/2/3 | 文本 | 注入文案 Prompt |
| 价格区间 | 数字 | |
| 白底图 | 附件 | Nanobanana 生图时的参考图（ref_image） |
| 目标平台 | 多选 | 得物/小红书/抖音 |

### 表2 — 内容规划表 (`plan`)

操作者在此表填写任务配置并触发执行。

| 字段 | 类型 | 说明 |
|------|------|------|
| 确认执行 | 单选 | **触发字段**：填「是」或「立即执行」即触发 Poller |
| 执行状态 | 单选 | 待执行 / 执行中 / 完成 / 失败 |
| 关联SKU | 关联 | 指向表1 |
| 任务类型 | 单选 | AI全创作 / 图片实拍+AI文案 / 视频实拍+AI文案 |
| 目标平台 | 多选 | 得物/小红书/抖音 |
| 内容类型 | 多选 | 种草推荐 / 开箱测评 / 穿搭分享 / … |
| 图文数量 | 数字 | 要生成几组图文内容 |
| 每组图片数 | 数字 | 每组生成几张图（默认 4，当前配置 5）|
| 视频数量 | 数字 | |
| 文案模型 | 单选 | deepseek / gpt54 / kimi |
| 图片模型 | 单选 | Nanobanana 2 / volcengine-seedream |
| 视频模型 | 单选 | volcengine-seedance |
| 注入标签数 | 数字 | 从标签库随机选 N 个注入（默认 5）|

### 表3 — Prompt 记录表 (`prompt`)

系统自动生成，每个 group × 类型对应一条记录，操作者可在此查阅或手动修改 Prompt。

| 字段 | 类型 | 说明 |
|------|------|------|
| 提示词编号 | 文本 | `P_{plan_code}_{group_id}_{suffix}`，如 `P_T_260417_057_img01_C` |
| 关联规划 | 关联 | 指向表2 |
| 关联SKU | 关联 | 指向表1 |
| 分组ID | 文本 | img01 / img02 / vid01 |
| 提示词类型 | 单选 | 图文正文 / 图片生成 / 视频内容 / 视频脚本 |
| 总Prompt | 多行文本 | 文案：`[SYS]\n{system}\n[USR]\n{user}`；图片：master prompt |
| 子Prompt列表 | 多行文本 | JSON 数组，图片记录专用，每张图一条 sub-prompt |

**Suffix 约定：**
- `C`（Copy）= 文案 Prompt
- `I`（Image）= 图片生成 Prompt

### 表4 — 内容生成表 (`content`)

每组生成内容对应一条记录，自动创建，人工审核。

| 字段 | 类型 | 说明 |
|------|------|------|
| 内容编号 | 文本 | `{plan_code}_{group_id}`，如 `T_260417_057_img01` |
| 标题 / 正文 / 标签 | 文本 | AI 生成后写入 |
| 生成图片 | 附件 | 上传的图片文件 |
| 生成状态 | 单选 | 生成中 / **已生成** / **生成失败** |
| 审核状态 | 单选 | 待审核 / **已通过** / 已拒绝（已通过触发发布流程）|
| 素材文件夹路径 | 文本 | 本地存储路径，如 `D:/…/Pending_Content/T_260417_057/img01` |
| 失败原因 | 文本 | 生成失败时写入错误信息 |

### 表5 — 发布执行表 (`publish`)

内容审核通过后自动创建，操作者在此选择发布方式并触发发布。

| 字段 | 类型 | 说明 |
|------|------|------|
| 发布方式 | 单选 | 待定 / 得物自动发布 / 小红书手动 / 其他手动 |
| 发布状态 | 单选 | 待发布 / 发布中 / **已发布** / 发布失败 |
| 计划发布时间 | 日期时间 | |

### 表6 — 素材知识库 (`material`)

存储从竞品/爆款帖子采集的参考素材，可触发 AI 分析提炼规律。

| 字段 | 类型 | 说明 |
|------|------|------|
| 触发分析 | 单选 | **触发字段**：填「是」触发 MaterialAnalysis |
| 分析状态 | 单选 | 待分析 / 分析中 / 已完成 / 分析失败 |
| 标题公式 / 正文结构 / 情感触发点 | 文本 | AI 分析结果 |

### 表7 — 标签库 (`tag`)

| 字段 | 说明 |
|------|------|
| 标签名 | 含 # 号，如 `#手机壳` |
| 适用平台 | 得物/小红书/抖音 |
| 品类/行业 | 用于过滤匹配 |
| 权重分 | 用于排序优选 |

生成文案时，系统按「平台 + 品类」过滤标签库，按权重降序取前 N 个注入。

### 表8 — 内容策略表 (`strategy`)

**核心配置表**，定义每种内容类型的文案生成规则。

| 字段 | 说明 |
|------|------|
| 内容类型 | 种草推荐/开箱测评/… |
| 目标平台 | 得物/小红书/… |
| 品类 | 手机配件/… |
| 启用 | 是/否 |
| 系统提示词前缀 | LLM system prompt 的自定义前缀 |
| 文案叙事节点 | JSON 数组，定义正文的叙事骨架（节点顺序+指导语） |
| 标题写作指南 | 爆款标题公式，注入到 user prompt |
| 情绪基调 | 松弛感/兴奋感/专业理性/… |

**匹配逻辑：** `内容类型 + 目标平台 + 品类` 三字段完全匹配，有多条时取权重最高的一条。

### 表9 — ShotPlan 镜头脚本表 (`shotplan`)

定义同一组图片中各张的拍摄角色（全景/特写/持握/场景等）。

| 字段 | 说明 |
|------|------|
| 适用类型 | 图片/视频 |
| 内容类型 | 种草推荐/… |
| 品类 | 手机配件/… |
| 角色序列 | JSON 数组，每项含 `zh`（中文角色名）和 `guidance`（拍摄指导） |

### 表10 — 场景库 (`scene`)

定义图片的拍摄场景，每条记录是一个独立场景，支持随机轮转分配。

| 关键字段 | 说明 |
|---------|------|
| 场景ID | SC001 ~ SCxxx |
| 场景基底_英文 | 给图片模型的英文场景描述 |
| 场景描述_中文 | 给文案模型的中文场景描述，注入 user prompt |
| 风格基调词 | 如"购物时髦,商场女孩"，补充场景氛围 |
| 人物类型 | 真人出镜/手部入镜/无人物 |
| 性别倾向/年龄段/外貌风格/姿态倾向 | 人物描述字段 |
| 技术参数 | 时段光境/空间感/光线方向/色温/景深感/镜头感 |
| 排除描述 | 告诉模型不要出现的元素 |
| 权重 | 场景分配时的优先级（越高越常被选中）|

### 表11 — SKU 统计表 (`sku_stats`)

汇总每个 SKU 的内容生产量、发布量等统计数据（仅读，由 syncer 维护）。

---

## 4. 任务类型与触发机制

### 4.1 触发条件一览

| 监听表 | 触发字段 | 触发值 | 任务类型 |
|--------|---------|--------|---------|
| 表2 规划表 | 确认执行 | 「是」或「立即执行」 | `TASK_CONTENT_GENERATION` |
| 表4 内容表 | 确认搬迁 | 「是」且搬迁状态=待搬迁 | `TASK_MATERIAL_MIGRATION` |
| 表4 内容表 | 审核状态 | 「已通过」 | `TASK_PUBLISH_RECORD_CREATE` |
| 表5 发布表 | 发布方式≠待定 | 且发布状态=待发布 | `TASK_PUBLISH` |
| 表6 素材表 | 触发分析 | 「是」 | `TASK_MATERIAL_ANALYSIS` |

### 4.2 防重复机制

Poller 发现触发条件后**立即**将状态字段改为中间态（如「执行中」），再入队。下次轮询时该记录已被锁定，不会重复入队。

### 4.3 任务类型说明

| 任务类型 | 文案 | 图片 | 说明 |
|---------|------|------|------|
| AI全创作 | AI生成 | AI生成 | 完全自动 |
| 图片实拍+AI文案 | AI生成 | 人工上传后搬迁 | 图片需操作者手动上传到表4 |
| 视频实拍+AI文案 | AI生成 | — | 视频由人工录制后搬迁 |

---

## 5. 内容生成全流程

`ContentGenerationHandler.__call__(task)` 是核心入口，完整流程如下：

```
表2规划记录
    │
    ▼ 1. 读取规划配置
    │  · 任务类型 / 目标平台 / 内容类型 / 模型选择
    │  · 图文数量(img_count) / 每组图片数(img_per_piece)
    │  · 关联SKU字段（颜色/材质/卖点等）
    │
    ▼ 2. _build_groups()  → groups[]
    │  · 按 img_count + vid_count 生成分组列表
    │  · 多 content_type 时轮转分配（随机起始偏移）
    │  · 输出：[{group_id:"img01", type:"img", content_type:"种草推荐", img_per_piece:5}, ...]
    │
    ▼ 3. _pick_tags()  → tags[]
    │  · 按平台+品类过滤标签库，权重降序取 tag_inject_n 个
    │
    ▼ 4. _build_prompt_records()  → prompt_records[]
    │  · 每个 group 创建 C（文案）和 I（图片/视频）两条 Prompt 记录到表3
    │  · 已存在则复用（dedup by 提示词编号）
    │
    ▼ 5. _assign_scenes()  → scene_assignments{}
    │  · 按平台+品类+人物类型 过滤场景库，权重降序排成 pool
    │  · 随机起始偏移，轮转分配每个 group 一个场景
    │  · 写入 plan.json 持久化
    │
    ▼ 6. _fill_prompts()  → 写入表3
    │  ├── 文案Prompt（suffix=C）
    │  │   · _lookup_strategy() 查表8策略
    │  │   · _build_text_prompts_from_strategy() 构建 system + user prompt
    │  │     含：叙事节点 / 场景块 / 篇次差异化指令（group_index/total_groups）
    │  │   · 格式：[SYS]\n{system}\n[USR]\n{user} 写入 总Prompt
    │  │
    │  └── 图片Prompt（suffix=I）
    │      · _lookup_strategy() + _lookup_shotplan()
    │      · _build_image_master_prompt() → 总Prompt（master）
    │      · _build_image_sub_prompts() → 子Prompt列表（JSON数组）
    │
    ▼ 7. _generate_content()  → 写入表4 + 本地文件
    │
    │  for each group:
    │  ├── 文案生成（AI全创作/图片实拍+AI文案/视频实拍+AI文案 均执行）
    │  │   · 从表3读回 总Prompt，拆分 [SYS]/[USR]
    │  │   · 注入 prior_titles 防重复指令（非首篇）
    │  │   · text_adapter.complete(system, user) → 标题/正文
    │  │   · 写入表4（标题/正文/标签）+ 本地 title.txt/body_tags.txt
    │  │
    │  └── 图片生成（仅 AI全创作）
    │      · 从表3读回 总Prompt（master）+ 子Prompt列表
    │      · for idx in range(img_count):
    │        · 若本地已存在 img_{n}.jpg → 跳过（重试保护）
    │        · combined = master + "\n\n---\n\n" + sub_prompts[idx]
    │        · img_adapter.generate(combined, ref_images) → bytes
    │        · 上传到表4附件 + 保存到本地 img_0N.jpg
    │      · 若任意图片失败 → fail_reason → 整组状态="生成失败"（可重试）
    │
    ▼ 8. 结果收尾
       · 成功 → 表2执行状态="完成"，表4生成状态="已生成"
       · 失败 → 表2执行状态="失败"，飞书群通知
```

### 5.1 plan_code 命名规则

```
T_{YYMMDD}_{序号三位}
例：T_260417_057
```

### 5.2 content_code 命名规则

```
{plan_code}_{group_id}
例：T_260417_057_img01
```

### 5.3 prompt_code 命名规则

```
P_{plan_code}_{group_id}_{suffix}
例：P_T_260417_057_img01_C   ← 文案Prompt
    P_T_260417_057_img01_I   ← 图片Prompt
```

---

## 6. 提示词构建详解

### 6.1 文案 Prompt（`_build_text_prompts_from_strategy`）

**输入：** Strategy 记录 + SKU 摘要 + 平台 + 内容类型 + 场景 + group_index + total_groups

**System Prompt 结构：**
```
{策略表8的系统提示词前缀}
（策略未配置时降级为内置角色设定）
```

**User Prompt 结构：**
```
请为以下产品生成「{content_type}」类型的完整内容（标题+正文）。

目标平台：{platform}
内容类型：{content_type}

产品信息：
{sku_summary}

场景设定（请将内容植入此场景氛围中）：{场景描述_中文}｜{风格基调词}

叙事结构（请按顺序展开）：
1. 【节点名】指导语
2. 【节点名】指导语
...

⚠️ 差异化要求：这是本产品第 N 篇笔记（共 M 篇）。
标题请采用「{title_pattern}」，叙事切入角度必须与其他篇次明显区分，
禁止重复相同的开头句式或叙事骨架。

输出格式：
【标题】
<标题（≤20字）>
参考方向：{标题写作指南}

【正文】
<正文（300-800字）>
```

**标题句式轮转（group_index 对应）：**

| group_index | 指定句式 |
|-------------|---------|
| 1 | 疑问句式（如：为什么我…？）|
| 2 | 数字/对比句式（如：买了X件才发现…）|
| 3 | 场景直述句式（如：健身/通勤/约会时…）|
| 4 | 反转/意外句式（如：没想到一条链子竟然…）|
| 5+ | 情绪共鸣句式（如：那种感觉就是…）|

**生成阶段追加 prior_titles（`_generate_content`）：**

从第 2 组开始，system prompt 末尾追加：
```
⚠️ 本批次已生成以下标题，新内容的标题句式和叙事角度必须与之明显不同，
禁止复用相同的开头词或句型结构：
  - {第1组标题}
  - {第2组标题}
  ...
```

**生成后格式解析（`_parse_text_result`）：** 提取 `【标题】` 和 `【正文】` 之间的内容。

---

### 6.2 图片 Master Prompt（`_build_image_master_prompt`）

**作用：** 提供整组图片的产品描述、人物设定、一致性要求。每组所有图片共享同一 master，每次生成前与 sub-prompt 拼接。

**结构（中文，目标 ≤600 字符）：**
```
【产品】{产品简称}，{颜色}色，{材质}材质，{风格}风格
【挂接规范】手机链通过手机壳底部中间挂绳孔或侧边孔穿入固定，链条自然垂坠…
（字段不超长时保留技术参数和排除描述）

【场景】{场景描述_中文}
风格：{风格基调词}。情绪：{情绪基调对应中文}。

【人物】{人物类型}，{性别倾向}，{年龄段}，{外貌风格}，{姿态倾向}

【一致性要求】
- 所有图片保持完全相同的产品外观（颜色、材质、细节）
- 同一人物（同一人、同套服装、同款发型）
- 统一光线和色彩风格贯穿始终
```

**长度超限时的裁剪优先级（低→高保留）：**
1. 删除【技术参数】
2. 缩短【避免】到第一个分句
3. 删除【避免】
4. 场景描述截断为前 60 字符

---

### 6.3 图片 Sub-Prompts（`_build_image_sub_prompts`）

**作用：** 每张图一条，定义该张图的具体镜头角色。

**单条 sub-prompt 结构：**
```
第N张：{镜头角色}：{拍摄指导}，{场景描述_中文}，
画面中有{人物类型}（{gender}、{age}、{外貌风格}、{姿态倾向}），
【一致性约束】本组所有图片为同一人物（{gender}、{age}、{外貌风格}）：
保持完全相同的服装（颜色/款式/细节）、相同发型、相同面孔特征，禁止更换服装或人物
```

> **关键设计：** 一致性约束中锚定了 gender + age + 外貌风格（不含 posture，因 posture 每张不同），使模型有具体的外貌参照，而不是空泛的"同一人物"。

**镜头角色来源（ShotPlan）：** `_lookup_shotplan()` 按「图片/视频 + 内容类型 + 品类」查表9，读取`角色序列` JSON 数组。ShotPlan 不存在时回退到内置默认角色。

**内置默认角色序列：**
```
全景展示  特写细节  持握场景  环境搭配  (循环)
```

---

### 6.4 生成时 Prompt 拼接（`_generate_content`）

```python
combined = f"{master_prompt}\n\n---\n\n{sub_prompts[idx]}"

# Nanobanana（Gemini）
img_bytes = img_adapter.generate(combined, ref_images=[白底图bytes])

# 其他适配器（volcengine-seedream 等）
img_bytes = img_adapter.generate(combined)
```

> **重要：** 所有适配器均传入 combined（master + sub），确保一致性要求和人物描述在每次 API 调用中都存在。

---

## 7. AI 模型适配器

配置文件：`middleware/config/model_params.yaml`

### 7.1 文案模型（TextModelAdapter）

| 模型标识 | 实际模型 | API 地址 |
|---------|---------|---------|
| `deepseek` | DeepSeek Chat | https://api.deepseek.com |
| `gpt54` | GPT-4 系列 | https://…runapi.co |
| `kimi` | Moonshot Kimi | https://api.moonshot.cn |

**接口：** `text_adapter.complete(system: str, user: str) → str`

### 7.2 图片模型（ImageModelAdapter）

| 模型标识 | 实际模型 | 说明 |
|---------|---------|------|
| `nanobanana-2` | gemini-3.1-flash-image-preview（via runapi.co）| 支持 ref_images（白底图）；响应可为 inlineData(base64) 或 fileData(URL)，适配器自动处理 |
| `volcengine-seedream` | 火山引擎 SeeDream | 纯文本→图片 |

**接口：** `img_adapter.generate(prompt: str, ref_images: list[bytes] | None) → bytes`

**Nanobanana 请求格式：**
```json
{
  "contents": [{
    "role": "user",
    "parts": [
      {"inlineData": {"mimeType": "image/jpeg", "data": "<base64_白底图>"}},
      {"text": "<combined_prompt>"}
    ]
  }],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"],
    "imageConfig": {"aspectRatio": "9:16", "imageSize": "1K"}
  }
}
```

**重试机制：** 最多 4 次，指数退避（1s → 3s → 9s）。

### 7.3 视频模型（VideoModelAdapter）

| 模型标识 | 实际模型 |
|---------|---------|
| `volcengine-seedance` | 火山引擎 Seedance |

**接口：** `vid_adapter.generate(prompt, min_seconds, max_seconds) → bytes`

---

## 8. 本地存储与数据库

### 8.1 本地文件存储（LocalStorage）

根目录：`D:/AI-Content-Hub/content-store/`（由 `LOCAL_STORAGE_ROOT` 环境变量配置）

**目录结构：**
```
content-store/
├── Pending_Content/          ← 生成完成，待审核/待发布
│   └── {plan_code}/
│       ├── plan.json         ← 规划元数据（模型选择/场景分配等）
│       └── {group_id}/
│           ├── content.json  ← 内容元数据（标题/正文/图片列表/状态）
│           ├── title.txt
│           ├── body_tags.txt
│           ├── img_01.jpg
│           ├── img_02.jpg
│           └── ...
└── archive/                  ← 发布后归档（按年月分类）
    └── {YYYY-MM}/
        └── {plan_code}/
```

**content.json 结构：**
```json
{
  "content_code": "T_260417_057_img01",
  "plan_code": "T_260417_057",
  "group_id": "img01",
  "feishu_record_id": "recvh2ql9oqdze",
  "platform": "得物",
  "content_type": "种草推荐",
  "content_form": "图文",
  "title": "...",
  "body": "...",
  "tags": "#开箱推荐 #得物好物 ...",
  "images": ["img_01.jpg", "img_02.jpg", "img_03.jpg", "img_04.jpg", "img_05.jpg"],
  "video": null,
  "status": "generated",
  "created_at": "2026-04-17T17:16:32",
  "updated_at": "2026-04-17T17:26:43"
}
```

### 8.2 SQLite 本地数据库（hub.db）

路径：`D:/AI-Content-Hub/data/hub.db`（Windows）

**主要表：**

| 表名 | 对应飞书表 | 用途 |
|------|---------|------|
| `skus` | 表1 | SKU 信息镜像 |
| `plans` | 表2 | 规划记录 + 本地状态机 |
| `prompts` | 表3 | Prompt 记录镜像 |
| `contents` | 表4 | 内容记录 + 本地状态机 |
| `publish_records` | 表5 | 发布记录 + 状态机 |
| `materials` | 表6 | 素材库镜像 |
| `tags` | 表7 | 标签库镜像 |
| `task_logs` | — | 任务执行日志（不同步飞书）|
| `sync_cursors` | — | 增量同步游标 |

**同步机制：**
- 启动时执行一次全量同步
- 之后每 5 分钟增量同步（FeishuSyncer）
- SQLite 开启 WAL 模式，支持读写并发

---

## 9. 发布流程

```
表4 审核状态="已通过"
    │
    ▼ PublishRecordCreatorHandler
    │  · 在表5创建发布记录（发布状态=待发布，发布方式=待定）
    │  · 发飞书通知提醒人工选择发布方式
    │
    ▼（人工在表5选择发布方式）
    │
    ▼ Poller 检测到：发布方式≠待定 AND 发布状态=待发布
    │
    ▼ PublishHandler
      ├── 得物自动发布：调用 publish-engine（Playwright 自动化）
      └── 手动方式：更新状态为"已发布"，无自动操作
```

---

## 10. 素材搬迁与分析

### 10.1 素材搬迁（MaterialMigrationHandler）

**触发：** 表4「确认搬迁=是」AND「搬迁状态=待搬迁」

**适用场景：** 任务类型为「图片实拍+AI文案」或「视频实拍+AI文案」，操作者手动上传图片/视频到表4 → 中台将附件下载到本地 + 整理到对应 group 目录。

### 10.2 素材分析（MaterialAnalysisHandler）

**触发：** 表6「触发分析=是」

**功能：** 调用文案模型分析采集到的竞品内容，提炼标题公式、正文结构、情感触发点等，写回表6 AI 分析字段，供运营参考优化策略配置。

---

## 11. 配置参考

### 11.1 环境变量（`middleware/.env`）

```ini
# 飞书应用
LARK_APP_ID=cli_xxxxxxxx
LARK_APP_SECRET=xxxxxxxx
LARK_BASE_TOKEN=Xxxxxxxxx       # 多维表格 Base ID

# AI 模型密钥
GPT54_API_KEY=sk-proj-...
KIMI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
NANOBANANA_API_KEY=sk-...       # runapi.co 密钥
VOLCENGINE_API_KEY=xxxxxxxx-...-...-...-xxxxxxxx

# 本地存储
LOCAL_STORAGE_ROOT=D:/AI-Content-Hub/content-store
```

### 11.2 `middleware/config/system.yaml` 关键项

```yaml
feishu:
  app_id: ${LARK_APP_ID}
  app_secret: ${LARK_APP_SECRET}
  base_token: ${LARK_BASE_TOKEN}
  tables:
    sku:       tblf9FAsQuUzvCzK
    plan:      tblDJ2hCvl7y4x5s
    prompt:    tbljMPKdYbGTb1K7
    content:   tblieT8ZK8HOQt0x
    publish:   tblLbA8gjwYbaMLB
    material:  tblGJiZBPiK2OdoO
    tag:       tblsnxUwqY1WgEAQ
    strategy:  tblu2EzR78tWjYf6
    shotplan:  tbl0xCaqru1TjwzK
    scene:     tbliWlwiyA4sppgY
    sku_stats: tblJRHExnxytve7s

poller:
  interval_seconds: 10   # 轮询间隔

notifications:
  enabled: true
  chat_id: oc_2a18512a...       # 飞书群 ID
  notify_on:
    queued: false
    success: true
    failure: true
```

### 11.3 `middleware/config/model_params.yaml` 关键项

```yaml
text_model:
  providers:
    deepseek:
      api_key: ${DEEPSEEK_API_KEY}
      base_url: https://api.deepseek.com
      model: deepseek-chat

image_model:
  providers:
    nanobanana-2:
      api_key: ${NANOBANANA_API_KEY}
      base_url: https://runapi.co
      model: gemini-3.1-flash-image-preview
      aspect_ratio: "9:16"
      image_size: "1K"
    volcengine-seedream:
      api_key: ${VOLCENGINE_API_KEY}
      ...
```

---

## 12. 运维操作手册

### 12.1 启动与停止

**Windows：**
```bat
cd D:\AI-Content-Hub\middleware
run_middleware.bat
```

**Mac/Linux：**
```bash
cd ~/openclaw/workspace/AI-Content-Hub/middleware
bash start.sh
```

**优雅停止：** `Ctrl+C` 触发 SIGINT，Poller 和 Dispatcher 优雅退出。

**日志文件：** `D:/AI-Content-Hub/logs/middleware.log`（10MB 滚动，保留 5 份）

---

### 12.2 新建内容生成任务（标准操作流程）

1. 在飞书**表1-SKU**确认目标商品已录入，白底图已上传
2. 在飞书**表8-策略**确认对应平台+品类+内容类型的策略记录已启用，叙事节点和标题写作指南已填写
3. 在飞书**表9-ShotPlan**确认对应品类+内容类型有镜头脚本
4. 打开飞书**表2-规划表**，新建一条记录，填写：
   - 关联 SKU
   - 任务类型（AI全创作）
   - 目标平台
   - 内容类型（可多选）
   - 图文数量 / 每组图片数
   - 文案模型 / 图片模型
5. 将「确认执行」改为「是」
6. 等待约 2~10 分钟（视 AI API 响应速度），刷新表4查看生成结果
7. 在表4审核内容，满意后将「审核状态」改为「已通过」
8. 在表5选择发布方式，等待自动发布或手动发布

---

### 12.3 任务失败重试

**文案+图片全部失败：**
- 表2执行状态变为「失败」
- 将执行状态改回「待执行」，再将「确认执行」改为「是」即可重新触发

**部分图片失败（如缺 img_03）：**
- 表4对应记录生成状态为「生成失败」
- 再次将表2「确认执行」改为「是」，系统重试时会自动跳过已存在的本地图片，只补生成缺失的

**手动补图工具：**
```bash
python scripts/repair_missing_img.py T_260417_057 img01 img03
```

---

### 12.4 Nanobanana 接口监控

接口偶发 429/400，可定期运行检测脚本：
```bash
python scripts/check_nanobanana.py
# 退出码 0=正常，1=不可用
# 恢复时自动发飞书群通知
```

也可用 crontab 设置定期检测：
```cron
*/15 * * * * cd /path/to/AI-Content-Hub && python scripts/check_nanobanana.py >> logs/nanobanana_check.log 2>&1
```

---

### 12.5 常见问题排查

| 现象 | 可能原因 | 处理方式 |
|------|---------|---------|
| 表2触发后表4无记录 | middleware 未启动 / 飞书 token 过期 | 检查 middleware 进程 + 日志 |
| 文案生成失败 | 文案模型 API key 失效 / 余额不足 | 更新 `.env` 中对应 API key 后重启 |
| 图片全部失败 (401) | NANOBANANA_API_KEY 过期 | 更新 `.env` 后重启（**注意需要重启**，配置在启动时加载） |
| 图片全部失败 (429) | runapi.co 配额耗尽 | 充值或等待配额重置 |
| 同组图片人物不一致 | 场景人物描述字段未填写 | 在表10场景库补充「外貌风格」「性别倾向」「年龄段」字段 |
| 多组内容标题重复 | 内容类型只配置了一种 | 可在表2多选几种内容类型，或确认表8策略的叙事节点差异明显 |
| 本地图片已有但飞书附件缺失 | 上传时网络超时 | 运行 `repair_missing_img.py` 补传 |

---

### 12.6 更新 API 密钥

1. 编辑 `middleware/.env`，替换对应密钥
2. **重启 middleware**（配置在启动时一次性加载，运行中修改 .env 不会生效）
3. 用 `check_nanobanana.py` 等工具验证新密钥是否正常

---

### 12.7 添加新场景

1. 在飞书**表10-场景库**新增一条记录
2. 必填字段：场景基底_英文、场景描述_中文、风格基调词、人物类型、外貌风格、性别倾向、年龄段
3. 推荐填写：光线方向、景深感、镜头感（影响图片质量）
4. 设置权重（1-100），越高越常被分配
5. 下次任务触发时自动生效（无需重启）

---

### 12.8 添加/修改内容策略

1. 在飞书**表8-策略表**新增或编辑记录
2. 确保「启用」字段为「是」
3. 「文案叙事节点」填写 JSON 格式：
   ```json
   [
     {"index": 1, "zh": "引入场景", "guidance": "用1-2句话描述使用场景，引发共鸣"},
     {"index": 2, "zh": "发现产品", "guidance": "自然引出产品，避免广告感"},
     {"index": 3, "zh": "质感描述", "guidance": "聚焦产品最核心的视觉/触感卖点"},
     {"index": 4, "zh": "搭配理由", "guidance": "解释为什么这款产品适合这个场景"},
     {"index": 5, "zh": "情感收尾", "guidance": "以情感共鸣或行动引导收尾"}
   ]
   ```
4. 「标题写作指南」示例：
   ```
   公式选一：①数字冲击（"3秒让手机链颜值×10"）②场景痛点（"出门总被问链子哪买的"）③反转悬念（"以为只是条链子，没想到…"）
   要求：含emoji或符号、口语化、禁止平铺产品描述
   ```
5. 改动立即生效，下次任务触发时使用新策略

---

*文档由 Claude 根据代码自动生成，如发现与实际代码不符请以代码为准。*
*最后更新：2026-04-17*
