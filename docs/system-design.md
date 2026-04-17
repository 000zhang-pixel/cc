# AI-Content-Hub 系统设计与使用文档

> 版本：2026-04-18 v2 | 适用分支：main

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
- 从飞书规划表触发，自动完成"SKU 信息 → 场景/人设分配 → Creative Brief → Prompt 构建 → 文案/图片/视频生成 → 结果回写飞书 + 本地存档"的全链路
- 支持多种任务类型：纯 AI 全创作、图片实拍配 AI 文案、视频实拍配 AI 文案
- 多模型支持（DeepSeek / GPT / Kimi 写文案，Nanobanana-Gemini / 火山引擎 生图，火山引擎 Seedance 生视频）
- **Creative Brief 层（v2）**：为每组内容预先构建统一意图包，文案/图片 Prompt 共享同一上下文，差异化显式建模
- **Persona 人设模板（v2）**：支持独立人设表驱动图片人物描述，实现跨组人设轮换
- 内置四维差异化机制：标题句式 / 叙事角度 / 人设 / 场景 同时拉开多组差异
- 内置一致性约束：Persona 锚点 + 组内所有图片共享同一 Master Prompt，人物外貌/服装/发型强一致
- **可观测性（v2）**：表3/表4/content.json 全链路记录 Brief、策略命中、失败 index

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                  飞书多维表格（云端）                      │
│  表1-SKU  表2-规划  表3-Prompt  表4-内容  表5-发布        │
│  表6-素材  表7-标签  表8-策略   表9-ShotPlan  表10-场景   │
│  表11-SKU统计  表12-Persona人设模板（v2新增）              │
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

系统使用 12 张飞书表，均在同一个 Base（多维表格文档）下。表12 为 v2 新增，需手动建表后在 `system.yaml` 填入 table_id。

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
| **差异化强度** | 单选 | **v2** 低 / 中（默认）/ 高 — 控制多组叙事角度拉开幅度 |
| **人设模式** | 单选 | **v2** 自动（默认）/ 固定主人设 / 多人设轮换 |
| **一致性强度** | 单选 | **v2** 中 / 强（默认）— 控制组内图片一致性约束力度 |
| **场景丰富度** | 单选 | **v2** 低 / 中（默认）/ 高 — 影响场景切换幅度 |

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
| **创意包摘要** | 多行文本 | **v2** 人设+场景+叙事角度可读摘要（系统自动写入） |
| **创意包JSON** | 多行文本 | **v2** 完整 Creative Brief JSON（调试用） |
| **命中策略ID** | 文本 | **v2** 实际使用的 Strategy record_id |
| **命中场景ID** | 文本 | **v2** 实际使用的 Scene 编号 |
| **命中人设ID** | 文本 | **v2** 实际使用的 Persona 编号 |
| **命中ShotPlanID** | 文本 | **v2** 实际使用的 ShotPlan record_id |
| **标题句式** | 文本 | **v2** 要求使用的标题句式（如：疑问句式） |
| **叙事角度** | 文本 | **v2** 要求使用的叙事切入角度（如：搭配点睛） |
| **一致性锚点** | 多行文本 | **v2** 本组图片人物一致性约束摘要 |
| **是否兜底生成** | 单选 | **v2** 是 / 否 — 是否命中默认逻辑而非配置逻辑 |

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
| **创意包摘要** | 多行文本 | **v2** 人设+场景+叙事角度可读摘要（系统自动写入） |
| **命中策略ID** | 文本 | **v2** 实际使用的 Strategy |
| **命中场景ID** | 文本 | **v2** 实际使用的 Scene |
| **命中人设ID** | 文本 | **v2** 实际使用的 Persona |
| **命中ShotPlanID** | 文本 | **v2** 实际使用的 ShotPlan |
| **标题句式** | 文本 | **v2** 实际要求的标题句式 |
| **叙事角度** | 文本 | **v2** 实际要求的叙事切入角度 |
| **组内一致性锚点** | 多行文本 | **v2** 图片一致性约束摘要 |

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
| **叙事角度标签** | **v2** 多选：搭配点睛 / 日常实用 / 细节质感 / 氛围感种草 / 礼物推荐 |
| **结构模式** | **v2** 单选：场景切入 / 痛点切入 / 体验切入 / 对比切入 / 情绪切入 |
| **标题句式池** | **v2** JSON 数组，配置后替代代码内置硬编码池，如 `["疑问句式","数字/对比句式","反转句式"]` |
| **正文禁忌** | **v2** 禁止出现的表达，如过硬广告腔（注入 system prompt） |
| **差异化提示模板** | **v2** 自定义篇次差异化提示，支持 `{group_index}` `{total_groups}` `{title_pattern}` `{narrative_angle}` 占位符 |
| **人设适配标签** | **v2** 多选，与表12气质标签联动，备用 |

**匹配逻辑：** `内容类型 + 目标平台 + 品类` 三字段完全匹配，有多条时取权重最高的一条。

**推荐标题句式池（可直接填入「标题句式池」JSON 字段，按品类调整示例词）：**

> 完整句式池（25 组），将以下 JSON 数组填入飞书表8对应策略记录的「标题句式池」字段后，代码自动按 group_index 轮转选用，完全替代内置硬编码池。

```json
[
  "疑问句式（为什么我的手机看起来比你的高级？）",
  "数字/对比句式（买了3条手机链才发现这款才是天花板）",
  "场景直述句式（通勤路上被问了10次手机链哪里买的）",
  "反转/意外句式（本来只想买个手机壳，没想到整个包都升级了）",
  "情绪共鸣句式（那种每次拿出手机都想炫耀的感觉）",
  "假设/如果句式（如果你的手机也能这么好看，你还会换吗）",
  "身份共鸣句式（手机链女孩都知道这个选法）",
  "宝藏安利句式（宝！你的手机链应该这样选）",
  "夸张感叹句式（救命这条手机链也太好看了吧！）",
  "吐槽痛点句式（你是不是也被问过：你的手机壳哪里买的）",
  "亲历感句式（用了一个月，说说我的真实体验）",
  "排比递进句式（一条链子，十种搭法，百种心情）",
  "对标比较句式（和大牌同款感，价格只要十分之一）",
  "悬念揭秘句式（终于找到了！那条被问烂的手机链）",
  "列举总结句式（选手机链别踩这5个坑，附避坑指南）",
  "强调最佳句式（这才是手机链的正确打开方式！）",
  "时间节点句式（入秋第一件新品，就是它了）",
  "地点场景句式（商场路人甲，靠一条链子拥有了品牌感）",
  "分析科普句式（为什么好看的手机链都有这个共同特征）",
  "互动征集句式（你是什么风格的手机链控？来对号入座）",
  "自白独白句式（承认吧，你换手机壳就是为了搭配手机链）",
  "节日送礼句式（送女朋友的手机链，这次她真的很喜欢）",
  "工作场景句式（打工人的手机链，颜值才是最高生产力）",
  "收藏攻略句式（手机链选购攻略，建议截图收藏）",
  "对比突出句式（同是白色系，为什么有的看起来更高级）"
]
```

| # | 句式类型 | 核心技巧 | 适用场景 |
|---|---------|---------|---------|
| 1 | 疑问句式 | 引发好奇，主动代入 | 种草推荐、开箱 |
| 2 | 数字/对比句式 | 具体数字增加可信度 | 多组评测、横评 |
| 3 | 场景直述句式 | 具体生活场景代入 | 通勤/校园/约会场景 |
| 4 | 反转/意外句式 | 出乎意料，吸引点开 | 开箱、体验类 |
| 5 | 情绪共鸣句式 | 感受先行，弱化产品 | 氛围感种草 |
| 6 | 假设/如果句式 | 带入美好预期 | 礼物推荐、生活升级 |
| 7 | 身份共鸣句式 | 圈层认同，制造专属感 | 垂直受众种草 |
| 8 | 宝藏安利句式 | 朋友感推荐，无广告感 | 日常实用推荐 |
| 9 | 夸张感叹句式 | 情绪拉满，博取点击 | 爆款新品、高颜值产品 |
| 10 | 吐槽痛点句式 | 共情用户痛点 | 解决方案型内容 |
| 11 | 亲历感句式 | 真实可信，降低防御 | 长期使用测评 |
| 12 | 排比递进句式 | 节奏感强，读感好 | 多功能/多搭法展示 |
| 13 | 对标比较句式 | 价值锚定，性价比凸显 | 平价好物推荐 |
| 14 | 悬念揭秘句式 | 制造悬念，强迫点开 | 高热问题解答 |
| 15 | 列举总结句式 | 实用导向，收藏率高 | 选购攻略、避坑指南 |
| 16 | 强调最佳句式 | 权威感、确定性强 | 推荐爆款/最佳选择 |
| 17 | 时间节点句式 | 季节/节日钩子 | 节日营销、换季种草 |
| 18 | 地点场景句式 | 具体场景画面感强 | 街拍、商场、咖啡馆场景 |
| 19 | 分析科普句式 | 专业感，知识型种草 | 深度测评、选购指南 |
| 20 | 互动征集句式 | 引发评论互动 | 互动型内容、话题引导 |
| 21 | 自白独白句式 | 真实感强，心理共鸣 | 情感型种草 |
| 22 | 节日送礼句式 | 送礼场景切入 | 节日礼物推荐 |
| 23 | 工作场景句式 | 打工人共情 | 职场/通勤场景 |
| 24 | 收藏攻略句式 | 干货内容，引导收藏 | 攻略型内容 |
| 25 | 对比突出句式 | 同类产品差异化 | 品质感、细节感种草 |

### 表9 — ShotPlan 镜头脚本表 (`shotplan`)

定义同一组图片中各张的拍摄角色（全景/特写/持握/场景等）。

| 字段 | 说明 |
|------|------|
| 适用类型 | 图片/视频 |
| 内容类型 | 种草推荐/… |
| 品类 | 手机配件/… |
| 角色序列 | JSON 数组，每项含 `zh`（中文角色名）和 `guidance`（拍摄指导） |
| **构图节奏** | **v2** 单选：稳定 / 丰富 / 跳跃 |
| **人物出镜比例** | **v2** 单选：无人物 / 少量 / 中等 / 高 |
| **近中远景配比** | **v2** 文本，如：2近景 + 2中景 + 1远景 |
| **道具密度** | **v2** 单选：低 / 中 / 高 |
| **动作变化要求** | **v2** 文本，注入 Sub-Prompt，如：持握、走动、抬手、侧转 |
| **禁止重复镜头** | **v2** 文本，注入 Sub-Prompt 约束，避免同组图片构图重复 |

### 表10 — 场景库 (`scene`)

定义图片的拍摄场景，每条记录是一个独立场景，支持随机轮转分配。

| 关键字段 | 说明 |
|---------|------|
| 场景ID | SC001 ~ SCxxx |
| 场景基底_英文 | 给图片模型的英文场景描述 |
| 场景描述_中文 | 给文案模型的中文场景描述，注入 user prompt |
| 风格基调词 | 如"购物时髦,商场女孩"，补充场景氛围 |
| 人物类型 | 真人出镜/手部入镜/无人物 |
| 性别倾向/年龄段/外貌风格/姿态倾向 | 人物描述字段（表12建立后可由 Persona 覆盖） |
| 技术参数 | 时段光境/空间感/光线方向/色温/景深感/镜头感 |
| 排除描述 | 告诉模型不要出现的元素 |
| 权重 | 场景分配时的优先级（越高越常被选中）|
| **场景主题** | **v2** 单选：商场 / 通勤 / 校园 / 居家 / 街头 / 咖啡馆 / 户外 |
| **氛围等级** | **v2** 单选：低 / 中 / 高 |
| **道具建议** | **v2** 文本，如：包、咖啡杯、耳机（注入 Image Master Prompt + 文案 Prompt）|
| **光线风格标签** | **v2** 多选：柔光 / 冷白光 / 暖调 / 背光 / 逆光 |
| **适合人设标签** | **v2** 多选，与表12气质标签联动 |
| **差异化备注** | **v2** 文本，说明该场景最适合拉开哪类差异 |

### 表11 — SKU 统计表 (`sku_stats`)

汇总每个 SKU 的内容生产量、发布量等统计数据（仅读，由 syncer 维护）。

### 表12 — Persona 人设模板表 (`persona`) — v2 新增

独立的人设模板层，解耦原来散落在 Scene 表中的人物描述，支持同 SKU 多组内容切换不同人设。

> **建表后操作**：在飞书创建该表，将 table_id 填入 `middleware/config/system.yaml` 的 `persona:` 字段。

| # | 字段 | 类型 | 说明 |
|---|------|------|------|
| 1 | 人设编号 | 文本 | 如 PS001，唯一标识 |
| 2 | 是否启用 | 单选 | 启用 / 停用 |
| 3 | 人设名称 | 文本 | 如：甜酷通勤女生 |
| 4 | 性别倾向 | 单选 | 女 / 男 / 中性 |
| 5 | 年龄段 | 单选 | 18-22 / 22-26 / 26-30 / 30+ |
| 6 | 外貌风格 | 文本 | 如：长发、轻妆、甜酷感 |
| 7 | 穿搭风格 | 文本 | 如：休闲通勤 / 极简时髦 |
| 8 | 气质标签 | 多选 | 甜酷 / 清冷 / 松弛 / 精致 / 青春 |
| 9 | 动作倾向 | 文本 | 如：自然持握、回头、低头看手机 |
| 10 | 适用品类 | 多选 | 手机链 / 手机壳 / 通用 |
| 11 | 适用内容类型 | 多选 | 种草推荐 / 穿搭搭配 / 场景展示 等 |
| 12 | 适合场景标签 | 多选 | 商场 / 校园 / 咖啡馆 / 街头 等 |
| 13 | Prompt描述模板 | 多行文本 | 用于图片 Master Prompt 的完整人物描述 |
| 14 | 一致性锚点模板 | 多行文本 | 组内一致性约束，如"同一女生，长发，轻妆，甜酷风，同套服装，同款发型，相同面孔特征" |
| 15 | 优先级 | 数字 | 同类候选中排序，越高越优先 |
| 16 | 备注 | 文本 | 说明用途 |

**人设分配规则：**
- 表12未配置时 → 自动回退到 Scene 表中的人物字段（零配置可运行）
- `人设模式=固定主人设` → 整单所有 group 共享优先级最高的 Persona
- `人设模式=多人设轮换`（默认）→ 不同 group 轮换 Persona，拉开视觉差异
- 同一 group 内所有图片共享同一 Persona（组内一致 / 组间差异）

**推荐人设库（可直接录入飞书表12）：**

| 编号 | 人设名称 | 气质标签 | 外貌风格 | 穿搭风格 | Prompt描述模板（简版） | 一致性锚点模板 |
|------|---------|---------|---------|---------|---------------------|--------------|
| PS001 | 甜酷通勤女生 | 甜酷 | 长黑发微卷，轻妆，猫眼眼线 | 休闲通勤，微甜oversize | Asian girl, ~22yo, long wavy black hair, light makeup with cat-eye liner, sweet-cool vibe, casual commute style | 同一女生，长黑发微卷，轻妆猫眼，甜酷通勤穿搭，同套服装，相同面孔 |
| PS002 | 清冷文艺女生 | 清冷 | 浅棕直发，无妆感，高级冷白 | 极简轻奢，米白/黑灰系 | Asian girl, ~24yo, straight light-brown hair, no-makeup look, cold-tone minimalist style, high-end vibe | 同一女生，浅棕直发，无妆感冷白皮，极简白黑穿搭，同套服装，相同面孔 |
| PS003 | 青春校园女生 | 青春 | 双马尾或丸子头，甜美清纯妆 | 学院风，格子/条纹/白衬衫 | Asian girl, ~19yo, twin tails or bun, sweet campus style, clean and youthful vibe | 同一女生，双马尾/丸子头，甜美清纯妆，学院风穿搭，同套服装，相同面孔 |
| PS004 | 精致都市白领 | 精致 | 黑直发或鲍勃，精致职场妆 | OL职场，西装/衬衫/裙摆 | Asian girl, ~27yo, sleek bob or straight black hair, polished office makeup, professional yet stylish | 同一女生，鲍勃/直发，精致职场妆，OL穿搭，同套服装，相同面孔 |
| PS005 | 松弛户外女孩 | 松弛 | 随意马尾或抓发，自然素颜感 | 运动休闲，卫衣/工装/帽子 | Asian girl, ~23yo, casual ponytail or messy bun, natural no-fuss look, sporty relaxed vibe | 同一女生，随意马尾，素颜自然感，运动休闲穿搭，同套服装，相同面孔 |
| PS006 | 时髦街拍女孩 | 精致 | 短发或蓬松中分，大气欧美妆 | 街头时尚，皮夹克/宽腿裤 | Asian girl, ~25yo, bold short hair or voluminous parted style, statement makeup, street fashion vibe | 同一女生，短发/中分蓬松，欧美妆容，街头时尚穿搭，同套服装，相同面孔 |
| PS007 | 甜美软妹女生 | 甜酷 | 自然卷/内扣发，粉嫩少女妆 | 甜美少女，粉色/花裙/蝴蝶结 | Asian girl, ~20yo, natural curls or C-curl hair, soft pink makeup, sweet girly style with bows | 同一女生，自然卷/内扣发，粉嫩少女妆，甜美粉色穿搭，同套服装，相同面孔 |
| PS008 | 知性学霸女生 | 清冷 | 黑直发马尾，斯文眼镜/无眼镜 | 学院风，条纹衬衫/针织开衫 | Asian girl, ~22yo, neat straight black hair in ponytail, scholarly elegant look, preppy academic style | 同一女生，黑直发马尾，知性斯文妆，学院条纹穿搭，同套服装，相同面孔 |
| PS009 | 复古港风女生 | 精致 | 微卷中发，复古红唇，高级感 | 港风复古，格纹西装/旗袍改良 | Asian girl, ~26yo, slightly wavy mid-length hair, retro red lip, Hong Kong vintage glamour | 同一女生，微卷中发，复古红唇妆，港风格纹穿搭，同套服装，相同面孔 |
| PS010 | 奶油韩系女生 | 青春 | 柔顺直发/空气刘海，韩式奶油妆 | 奶油系，米色/奶白/浅粉系 | Asian girl, ~21yo, silky straight hair with wispy bangs, Korean creamy soft makeup, muted pastel tones | 同一女生，柔顺直发空气刘海，韩系奶油妆，奶油色系穿搭，同套服装，相同面孔 |
| PS011 | 中性穿搭女生 | 松弛 | 短发或帽子压发，自然淡妆 | 中性休闲，帽衫/工装裤/板鞋 | Asian girl, ~23yo, short hair or baseball cap, natural light makeup, androgynous casual vibe | 同一女生，短发/帽子压发，自然淡妆，中性工装穿搭，同套服装，相同面孔 |
| PS012 | 氛围感摄影女孩 | 清冷 | 蓬松波浪发，迷离慵懒感，微烟熏 | 慵懒欧美，皮草/薄纱/单色系 | Asian girl, ~25yo, loose wavy hair, dreamy smoky eye makeup, ethereal moody fashion sense | 同一女生，蓬松波浪发，微烟熏慵懒妆，氛围感单色穿搭，同套服装，相同面孔 |

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
    │  · 图文数量 / 每组图片数
    │  · v2新增：差异化强度 / 人设模式 / 一致性强度 / 场景丰富度
    │
    ▼ 2. _build_groups()  → groups[]
    │  · 按 img_count + vid_count 生成分组列表
    │  · 多 content_type 时轮转分配（随机起始偏移）
    │
    ▼ 3. _fetch_tags()  → tags[]
    │  · 按平台+品类过滤标签库，权重降序取 tag_inject_n 个
    │  · 分层随机（60%前20 + 40%尾部）
    │
    ▼ 4. _assign_scenes()  → scene_assignments{}
    │  · 按品类过滤场景库，权重降序排成 pool
    │  · 随机起始偏移，轮转分配每个 group 一个场景
    │  · 写入 plan.json["scene_assignments"] 持久化
    │
    ▼ 5. _assign_personas()  → persona_assignments{}   ← v2 新增
    │  · 若表12已配置：按品类过滤 Persona，按优先级排序
    │    · 固定主人设模式：全部 group 共享 top 1 Persona
    │    · 多人设轮换模式：不同 group 轮换 Persona
    │  · 未配置时：从 Scene 人物字段派生伪 Persona（零配置可运行）
    │
    ▼ 6. _build_creative_briefs()  → briefs{}           ← v2 新增
    │  · 每个 group 构建一个 Brief：
    │    · title_pattern（轮转：疑问→数字→场景→反转→情绪共鸣）
    │    · narrative_angle（轮转：搭配点睛→日常实用→细节质感→…）
    │    · structure_mode（轮转）
    │    · consistency_anchor（来自 Persona 或 Scene 派生）
    │    · scene_id / persona_id（命中记录，用于可观测性）
    │  · 写入 plan.json["briefs"] 持久化
    │
    ▼ 7. _create_prompt_records()  → prompt_records[]
    │  · 每个 group 创建 C（文案）和 I（图片/视频）两条 Prompt 记录到表3
    │  · 已存在则复用（dedup by 提示词编号）
    │
    ▼ 8. _fill_prompts()  → 写入表3                    ← v2 升级
    │  ├── 文案Prompt（suffix=C）
    │  │   · _lookup_strategy() 查表8
    │  │   · _build_text_prompts_from_strategy(brief=brief, persona=persona)
    │  │     · Brief 提供 title_pattern + narrative_angle + structure_mode
    │  │     · 读取 Strategy 新字段：标题句式池 / 差异化提示模板
    │  │     · 场景 道具建议 → scene_block
    │  │     · Persona 气质/外貌 → persona_block（可选）
    │  │   · 格式：[SYS]\n{system}\n[USR]\n{user} 写入 总Prompt
    │  │   · 写表3观测字段：创意包摘要/创意包JSON/命中策略ID/标题句式/叙事角度/一致性锚点
    │  │
    │  └── 图片Prompt（suffix=I）
    │      · _lookup_shotplan() 查表9
    │      · _build_image_master_prompt(persona=persona, brief=brief)
    │        · Persona → 人物描述优先（覆盖 Scene 人物字段）
    │        · Brief consistency_anchor → 一致性要求
    │        · Scene 道具建议 → 【道具参考】块
    │      · _build_image_sub_prompts(persona=persona, brief=brief)
    │        · ShotPlan 新字段：禁止重复镜头 / 动作变化要求 → 注入构图约束
    │      · 写表3观测字段（同上）
    │
    ▼ 9. _generate_content()  → 写入表4 + 本地文件
    │
    │  for each group:
    │  ├── 文案生成（AI全创作/图片实拍+AI文案/视频实拍+AI文案 均执行）
    │  │   · 从表3读回 总Prompt，拆分 [SYS]/[USR]
    │  │   · 注入 prior_titles 防重复指令（非首篇）
    │  │   · text_adapter.complete(system, user) → 标题/正文
    │  │   · 写入表4（标题/正文/标签 + v2观测字段）
    │  │   · 写本地：title.txt / body_tags.txt / content.json debug块
    │  │
    │  └── 图片生成（仅 AI全创作）
    │      · 从表3读回 总Prompt（master）+ 子Prompt列表
    │      · for idx in range(img_count):
    │        · 若本地已存在 img_{n}.jpg → 跳过（重试保护）
    │        · combined = master + "\n\n---\n\n" + sub_prompts[idx]
    │        · img_adapter.generate(combined, ref_images) → bytes
    │        · 上传到表4附件 + 保存到本地 img_0N.jpg
    │        · 失败时记录 index → content.json debug.failed_image_indexes
    │      · 若任意图片失败 → fail_reason → 整组状态="生成失败"（可重试）
    │
    ▼ 10. 结果收尾
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

**输入：** Strategy 记录 + SKU 摘要 + 平台 + 内容类型 + 场景 + **Brief（v2）** + **Persona（v2，可选）**

**System Prompt 结构：**
```
{策略表8的系统提示词前缀}
（策略未配置时降级为内置角色设定）

⚠️ 绝对禁止出现以下表达：{正文禁忌}
← v2：若 Strategy 配置了「正文禁忌」字段，追加此约束段
```

**User Prompt 结构：**
```
请为以下产品生成「{content_type}」类型的完整内容（标题+正文）。

目标平台：{platform}
内容类型：{content_type}

产品信息：
{sku_summary}

场景设定（请将内容植入此场景氛围中）：{场景描述_中文}｜{风格基调词}
画面中可以出现：{道具建议}
← v2：Scene 配置了「道具建议」时追加，引导文案提及对应道具增加画面感

人物气质参考：{persona_name}，{外貌风格}，{穿搭风格}，{气质标签}
← v2：Persona 已配置时追加，引导文案中的人物描述与图片人设一致

叙事结构（请按顺序展开）：
1. 【节点名】指导语
2. 【节点名】指导语
...

⚠️ 差异化要求：这是本产品第 {group_index} 篇笔记（共 {total_groups} 篇）。
标题请采用「{title_pattern}」，叙事切入角度为「{narrative_angle}」，
切入角度必须与其他篇次明显不同，禁止重复相同的开头句式或叙事骨架。
← v2：若 Strategy 配置了「差异化提示模板」，以自定义模板整体替换本段（支持 {group_index}/{total_groups}/{title_pattern}/{narrative_angle} 占位符）

输出格式：
【标题】
<标题（≤20字）>
参考方向：{标题写作指南}

【正文】
<正文（300-800字）>
```

**标题句式（title_pattern）解析优先级（v2）：**

| 优先级 | 来源 | 说明 |
|-------|------|------|
| 1 | Strategy「标题句式池」JSON → 按 group_index 轮转 | 飞书表8配置句式池后完全替代内置池 |
| 2 | 内置硬编码池（5 种） | 最终兜底 |

**内置标题句式轮转（group_index 对应）：**

| group_index | 指定句式 | 示例 |
|-------------|---------|------|
| 1 | 疑问句式 | 为什么我的手机看起来比你的高级？ |
| 2 | 数字/对比句式 | 买了3条手机链才发现这款才是天花板 |
| 3 | 场景直述句式 | 通勤路上被问了10次手机链哪里买的 |
| 4 | 反转/意外句式 | 本来只想买个手机壳，没想到整个包都升级了 |
| 5+ | 情绪共鸣句式 | 那种每次拿出手机都想炫耀的感觉 |

**叙事角度（narrative_angle）轮转（v2）：**

| group_index | 叙事角度 | 切入重点 |
|-------------|---------|---------|
| 1 | 搭配点睛 | 强调产品与整体穿搭的加分效果 |
| 2 | 日常实用 | 聚焦产品在日常场景中的功能价值 |
| 3 | 细节质感 | 放大材质/工艺/手感等感官细节 |
| 4 | 氛围感种草 | 用情绪氛围感染读者，弱化产品硬广感 |
| 5+ | 礼物推荐 | 以"送礼"角度切入，强调心意和实用性 |

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

**v2 人物信息优先级：**

| 优先级 | 来源 | 说明 |
|-------|------|------|
| 1 | 表12 Persona.prompt_template | 若该 group 分配到 Persona，使用 Persona 的完整人物描述模板，覆盖 Scene 人物字段 |
| 2 | 表10 Scene 人物字段拼接 | Persona 未配置时，自动拼接 Scene 的人物类型/性别/年龄/外貌/姿态 |

**v2 一致性锚点优先级：**

| 优先级 | 来源 |
|-------|------|
| 1 | Persona.consistency_anchor_template（表12 一致性锚点模板，描述最精确）|
| 2 | Brief.consistency_anchor（由 Scene 字段派生）|
| 3 | 内置通用一致性模板 |

**结构（中文，目标 ≤600 字符）：**
```
【产品】{产品简称}，{颜色}色，{材质}材质，{风格}风格
【挂接规范】手机链通过手机壳底部中间挂绳孔或侧边孔穿入固定，链条自然垂坠…
（字段不超长时保留技术参数和排除描述）

【场景】{场景描述_中文}
风格：{风格基调词}。情绪：{情绪基调对应中文}。

【道具参考】{Scene.道具建议}
← v2：Scene 配置了「道具建议」时追加（如：包、咖啡杯、耳机）

【人物】{Persona.prompt_template}
← v2：Persona 已配置时使用（如："亚洲女生，约22岁，长黑发微卷，轻妆，甜酷感"）
← 无 Persona 时：{人物类型}，{性别倾向}，{年龄段}，{外貌风格}，{姿态倾向}

【一致性要求】
{Persona.consistency_anchor_template}
← v2：Persona 一致性锚点（如："同一女生，长发，轻妆，甜酷风，同套服装，同款发型，相同面孔特征"）
← 无 Persona 时使用内置模板：
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

**v2 人物信息优先级：** 同 6.2（Persona 覆盖 Scene 人物字段）

**单条 sub-prompt 结构：**
```
第N张：{镜头角色}：{拍摄指导}，{场景描述_中文}，
画面中有{人物类型}（{gender}、{age}、{外貌风格}、{姿态倾向}），
【一致性约束】{consistency_anchor}
（Persona 已配置时为精确锚点；否则为派生描述，如"本组同一女生/服装/发型"）

【构图约束】
← v2：若 ShotPlan 配置了相关字段时追加
动作要求：{动作变化要求}（各张采用不同动作，如：持握→走动→抬手→侧转）
禁止：{禁止重复镜头}（如：禁止连续两张出现相同正面全景）
```

> **关键设计：** 一致性约束中锚定了 gender + age + 外貌风格（不含 posture，因 posture 每张不同），使模型有具体的外貌参照。v2 中若 Persona 配置了一致性锚点模板，描述更精确（含服装色系、发型款式），效果显著优于仅靠 Scene 字段派生。

**构图约束注入（v2）：** 若 ShotPlan 中配置了以下字段，系统自动追加到每条 sub-prompt 末尾：
- **动作变化要求**：强制本组图片使用不同动作，避免同姿势重复出现
- **禁止重复镜头**：约束同组不出现相同构图（如：禁止连续两张相同正面全景）

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
  "updated_at": "2026-04-17T17:26:43",
  "debug": {
    "brief_summary": "人设:甜酷通勤女生 | 场景:SC003商场 | 叙事角度:搭配点睛 | 标题句式:疑问句式",
    "strategy_id": "recABCDE12345",
    "scene_id": "SC003",
    "persona_id": "PS001",
    "shotplan_id": "recXXXXXXXXXX",
    "failed_image_indexes": []
  }
}
```

**plan.json 结构（`Pending_Content/{plan_code}/plan.json`）：**
```json
{
  "plan_code": "T_260417_057",
  "sku_code": "SJL0413001",
  "platform": "得物",
  "content_types": ["种草推荐", "穿搭分享"],
  "img_count": 3,
  "img_per_group": 5,
  "text_model": "deepseek",
  "img_model": "nanobanana-2",
  "diff_strength": "中",
  "persona_mode": "多人设轮换",
  "consistency_strength": "强",
  "scene_variety": "中",
  "scene_assignments": {
    "img01": "SC003",
    "img02": "SC007",
    "img03": "SC011"
  },
  "briefs": {
    "img01": {
      "title_pattern": "疑问句式",
      "narrative_angle": "搭配点睛",
      "structure_mode": "场景切入",
      "consistency_anchor": "同一女生，长发，轻妆，甜酷风，同套服装，同款发型",
      "scene_id": "SC003",
      "persona_id": "PS001",
      "strategy_id": null,
      "shotplan_id": null
    },
    "img02": {
      "title_pattern": "数字/对比句式",
      "narrative_angle": "日常实用",
      "structure_mode": "痛点切入",
      "consistency_anchor": "同一女生，短发，清爽妆，极简风，同套服装",
      "scene_id": "SC007",
      "persona_id": "PS002",
      "strategy_id": null,
      "shotplan_id": null
    }
  },
  "created_at": "2026-04-17T17:15:00"
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
LARK_BASE_TOKEN=Xxxxxxxxx           # 多维表格 Base ID

# AI 模型密钥
GPT54_API_KEY=sk-proj-...
KIMI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
NANOBANANA_API_KEY=sk-...           # runapi.co 密钥
VOLCENGINE_API_KEY=xxxxxxxx-...-...-...-xxxxxxxx

# 本地存储
LOCAL_STORAGE_ROOT=D:/AI-Content-Hub/content-store

# 发布引擎（得物自动发布）
PUBLISH_ENGINE_SCRIPT=D:/AI-Content-Hub/publish-engine/publish_engine_v40.sh

# 飞书通知群
NOTIFICATION_CHAT_ID=oc_xxxxxxxx    # 飞书群 chat_id，用于发布成功/失败通知
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
    persona:   ""                 # v2 新增：表12 Persona人设模板表，建表后填入table_id

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

### 12.9 Persona 人设模板建表与配置（v2 新增）

#### 建表步骤

1. 在飞书 Base 中新建第 12 张表，命名为「Persona 人设模板」
2. 按 [表12 字段说明](#表12--persona-人设模板表-persona--v2-新增) 创建 16 个字段
3. 至少录入 3 条人设记录（「是否启用=启用」），建议覆盖不同气质类型（参见下方推荐人设库）
4. 复制表的 `table_id`（形如 `tblXXXXXXXX`，在飞书表格 URL 或表格设置中查看）
5. 编辑 `middleware/config/system.yaml`，将 `persona: ""` 改为实际 table_id：
   ```yaml
   persona: tblXXXXXXXX
   ```
6. **无需重启** middleware，下次任务触发时自动加载

#### 人设不生效排查

| 现象 | 原因 | 处理 |
|------|------|------|
| 图片人物与预期不符 | persona 字段为空串（未填 table_id）| 填入正确 table_id |
| 部分 group 无人设 | 人设记录数少于 group 数，轮转时复用 | 增加人设记录 |
| 人设被忽略 | 「是否启用」字段未设为「启用」| 检查每条人设记录 |
| Persona 无品类匹配 | 人设「适用品类」与 SKU 品类不一致 | 调整「适用品类」或设为「通用」|

#### 人设模式选择建议

| 场景 | 推荐人设模式 |
|------|------------|
| 单 SKU 希望建立固定 IP 感 | 固定主人设 |
| 多组内容希望视觉丰富、覆盖不同受众 | 多人设轮换（默认）|
| 未建人设表、快速出内容 | 自动（回退到 Scene 字段）|

---

*文档由 Claude 根据代码自动生成，如发现与实际代码不符请以代码为准。*
*最后更新：2026-04-18 v2*
