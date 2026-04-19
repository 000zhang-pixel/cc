# Feishu 四表整改归档（2026-04-19）

## 目标

归档自 2026-04-18 以来针对以下四张飞书多维表的字段、数据与业务逻辑调整，形成可回溯的变更说明与验证证据：

- 内容策略表（strategy）
- 拍摄方案表（shotplan）
- 视觉场景表（scene）
- Persona人设模板表（persona）

## 变更范围

### 代码与脚本

- `scripts/tables/definitions.py`
- `scripts/seed_shotplans.py`
- `scripts/remediate_tables.py`
- `middleware/handlers/content_generation.py`
- `middleware/adapters/feishu.py`
- `db/sync/syncer.py`

### 诊断/规划/审计产物

- `docs/plans/2026-04-18-feishu-four-table-remediation-plan.md`
- `docs/plans/2026-04-18-feishu-four-table-execution-table.csv`
- `tmp/remediation_report.json`
- `tmp/post_apply_audit.json`

---

## 一、表结构层变更

### 1) 内容策略表（strategy）

新增/强化字段：

- `标题写作指南`
- `标题句式池`
- `叙事角度标签`
- `结构模式`
- `正文禁忌`
- `差异化提示模板`
- `人设适配标签`

枚举/字段约束调整：

- `适用品类` 统一为 `手机壳 / 手机链 / 充电宝`
- `文案叙事节点` 约定为 JSON 数组文本

### 2) 拍摄方案表（shotplan）

新增字段：

- `构图节奏`
- `人物出镜比例`
- `近中远景配比`
- `道具密度`
- `动作变化要求`
- `禁止重复镜头`

枚举调整：

- `适用内容形态` 扩展并兼容 `图片 / 图片生成 / 组图 / 视频画面`
- `适用品类` 统一为 `手机壳 / 手机链 / 充电宝`

### 3) 视觉场景表（scene）

新增/强化字段：

- `场景主题`
- `氛围等级`
- `道具建议`
- `光线风格标签`
- `适合人设标签`
- `差异化备注`

枚举调整：

- `人物类型` 统一扩展为 `有人物·主体 / 有人物·局部 / 有人物·配角 / 无人物·纯产品 / 可有人物`
- `适用品类` 统一为 `手机壳 / 手机链 / 充电宝`

### 4) Persona 人设模板表（persona）

结构状态：

- 将 Persona 表定义完整纳入 `scripts/tables/definitions.py`
- 保持运行时核心字段不大改，主要做标签体系对齐

对齐字段范围：

- `气质标签`
- `适用品类`
- `适用内容类型`
- `适合场景标签`

---

## 二、数据层变更

### Dry-run 计划结果

来自 `tmp/remediation_report.json`：

| 表 | 更新 | 新增 |
|---|---:|---:|
| strategy | 30 | 4 |
| shotplan | 40 | 4 |
| scene | 94 | 6 |
| persona | 0 | 4 |

### 落地后记录规模

来自 `tmp/post_apply_audit.json`：

| 表 | 最终记录数 |
|---|---:|
| strategy | 34 |
| shotplan | 43 |
| scene | 103 |
| persona | 16 |

### 关键数据修复内容

#### strategy

- 为既有 30 条策略补齐高级增强字段
- 将 `文案叙事节点` 从箭头串/纯文本统一为 JSON 数组文本
- 新增 4 条围绕主营类目（手机壳/手机链）的策略模板

#### shotplan

- 统一旧 `适用内容形态` 到以 `图片` 为主的兼容枚举
- 清理旧内容类型映射，如 `产品展示 -> 好物分享`、`种草图文 -> 种草推荐`
- 为方案补齐 `动作变化要求` 与 `禁止重复镜头`
- 新增 4 条主营类目导向方案

#### scene

- 为既有场景补齐 `场景主题`、`道具建议`、`适合人设标签`
- 统一 `人物类型` 和异常品类值
- 补齐关键技术字段（姿态、光线、色温、景深、镜头感等）
- 新增 6 条主营类目/送礼/通勤/棚拍导向场景

#### persona

- 保持原有核心结构稳定
- 新增 4 条更贴近当前主营类目的主力人设

---

## 三、业务逻辑层变更

### 1) Feishu 写回路径

`middleware/adapters/feishu.py`

- 保留 SDK 读路径
- 新增 CLI 写路径，允许通过 `FEISHU_WRITE_BACKEND=cli` 切换到 `lark-cli --as user`
- 在初始化时校验 `lark-cli auth status --verify`
- 对 `update_record` / `create_record` 提供 CLI 写回能力
- 增加 CLI 写操作结构化日志

目的：

- 规避 bot/app 身份对 Bitable 写入的 `91403 Forbidden`
- 先以最小改动恢复生产关键写路径

### 2) 内容生成对新策略结构的兼容

`middleware/handlers/content_generation.py`

- 兼容 `文案叙事节点` 中的两种结构：
  - 结构化 dict 节点（含 `index/zh/node/guidance`）
  - 纯字符串节点
- 当结构化节点缺失时，自动回退为稳定文本输出

目的：

- 让新旧策略数据都能被消费
- 避免切换到 JSON 节点后 prompt 组装失败

### 3) 本地同步健壮性

`db/sync/syncer.py`

- 对单条记录 upsert 使用 nested transaction
- 捕获 `IntegrityError`，跳过冲突记录并继续同步
- 对 SKU 编号为空的记录直接跳过，避免无效本地写入

目的：

- 降低历史脏数据/重复数据导致整批同步中断的风险

---

## 四、验证证据

### 审计结果

来自 `tmp/post_apply_audit.json` 的落地后结果：

- strategy
  - `missing_advanced_fields = 0`
  - `non_json_story_nodes = 0`
  - `invalid_content_types = 0`
- shotplan
  - `invalid_forms = 0`
  - `legacy_content_types = 0`
  - `missing_constraints = 0`
  - `empty_categories = 0`
- scene
  - `missing_theme = 0`
  - `missing_props = 0`
  - `missing_persona_tags = 0`
  - `invalid_person_types = 0`
  - `invalid_categories = 0`
  - `missing_tech_fields = 0`
  - `invalid_theme = 0`
- persona
  - `missing_core_fields = 0`
  - `invalid_tags = 0`
  - `invalid_scene_tags = 0`

### 分布检查

- shotplan `适用内容形态` 分布：仅 `图片 = 43`
- scene `人物类型` 分布：
  - `有人物·主体 = 69`
  - `无人物·纯产品 = 25`
  - `有人物·配角 = 1`
  - `有人物·局部 = 6`
  - `可有人物 = 2`
- scene `适用品类` 分布：
  - `手机壳 = 38`
  - `手机链 = 97`
  - `充电宝 = 11`

---

## 五、剩余风险

1. Feishu CLI 写路径当前依赖 `lark-cli` 用户态登录，当前 mac 仍存在 `tokenStatus=needs_refresh` 风险。
2. 归档文档中的“落地后记录规模”与“零残留问题”基于现有审计 JSON；若线上表被外部再次修改，需要重新导出并复审。
3. 当前仓库工作区不仅包含四表整改，也包含 GPT-5.4 / Nanobanana / 同步健壮性等相关改动；提交时需要明确提交边界。

---

## 六、结论

本轮四表整改已形成完整闭环：

- 表结构已与当前主营类目和运行时需求对齐
- 数据层补值/新增已完成并有审计证据
- 业务逻辑已兼容新结构，并补强了 Feishu 写回与本地同步稳定性

若后续需要再次追溯，本文件应作为本轮整改的主归档入口，配合以下文件阅读：

- `docs/plans/2026-04-18-feishu-four-table-remediation-plan.md`
- `tmp/remediation_report.json`
- `tmp/post_apply_audit.json`
