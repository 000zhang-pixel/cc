# 需求文档：飞书群通知 + SKU发布统计表

> **状态：✅ 已全部实施完成**（2026-04-08）

---

## 背景

系统缺少两个运营反馈机制：
1. 发布状态变化（成功/失败/待发布）无任何主动通知，需要手动刷表才能知道结果
2. 无法快速看出每个 SKU 累计产出了多少内容、发布了多少、最近什么时候发布的

---

## 需求一：飞书群富文本卡片通知 ✅

### 触发时机与卡片样式

| 场景 | 触发位置 | 卡片颜色 | 包含字段 |
|------|---------|---------|---------|
| 新增待发布 | `publish_record_creator.py` 创建记录后 | 蓝色 | 发布编号、目标平台、内容形态、SKU、标题预览 |
| 发布成功 | `publish.py` `_publish_dewu()` 成功后 | 绿色 | 同上 + 发布时间、SKU累计发布次数 |
| 发布失败 | `publish.py` `__call__()` 异常后 | 红色 | 同上 + 失败原因、⚠️ 手动处理提示 |

### 实施步骤

| 步骤 | 内容 | 状态 |
|------|------|------|
| Step 1 | 飞书开发者后台开启 `im:message` 权限，机器人加入目标群 | ✅ |
| Step 2 | 获取目标群 chat_id：`oc_2a18512a232920019a216346de01379a` | ✅ |
| Step 3 | `feishu.py` 新增 `send_group_text()` + `send_group_card()` | ✅ |
| Step 4 | `system.yaml` 新增 `notifications.enabled/chat_id` | ✅ |
| Step 5 | `publish.py` 新增 `_notify_card_success()` / `_notify_card_failure()` | ✅ |
| Step 6 | `publish_record_creator.py` 新增 `_notify_card_queued()` | ✅ |
| Step 7 | `main.py` 透传 `notifications_cfg` 给两个 handler | ✅ |

### 关键配置

```yaml
# middleware/config/system.yaml
notifications:
  enabled: true
  chat_id: "oc_2a18512a232920019a216346de01379a"
  notify_on:
    queued: false    # 待发布进队 — Base表可查，默认静默
    success: true    # 发布成功 — 运营确认用，可关
    failure: true    # 发布失败 — 必报，需人工处理
```

**子开关说明**：
- `queued`：待发布进队通知，信息价值低（Base表本身可查队列），默认关闭
- `success`：发布成功通知，用于运营确认，可在发布高峰期手动关闭
- `failure`：发布失败通知，必报，需人工处理，建议始终开启

### 关键实现

**`feishu.py`**：
- `send_group_text(chat_id, text)` — 纯文本消息（保留备用）
- `send_group_card(chat_id, card)` — `msg_type="interactive"`，失败只 log warning，不影响主流程

**`publish.py`**：
- `_notify_card_success()` — 绿色卡片，底部附"该SKU累计发布成功 N 次"（读 sku_stats 表）
- `_notify_card_failure()` — 红色卡片，附失败原因 + ⚠️ 手动处理提示
- `_get_sku_stats_summary()` — 从统计表读当前发布成功数，用于卡片 footer

**`publish_record_creator.py`**：
- `_notify_card_queued()` — 蓝色卡片，从 content 记录读取平台/形态/标题/SKU

---

## 需求二：SKU发布统计表 ✅

### 表结构

> 原设计中 SKU编号/SKU名称/累计生成内容数 计划用 lookup 字段，但 lookup where 子句限制导致实现复杂，
> 最终决策：**全部改为可写字段，由中间件负责聚合写入**，更简洁可控。

**表名：SKU发布统计 | table_id：`tblJRHExnxytve7s`**

| 字段名 | 类型 | 实现方式 | 说明 |
|--------|------|---------|------|
| 关联SKU | link → 表1（tblf9FAsQuUzvCzK） | 代码写入 | 主关联，每行一个SKU |
| SKU编号 | text | 中间件写入 | 从 SKU 表复制 |
| SKU名称 | text | 中间件写入 | 从 SKU 表复制 |
| 累计生成内容数 | number | 中间件写入 | 该SKU关联的表4记录数 |
| 发布成功数 | number | 中间件写入 | 表5 发布状态=已发布 count |
| 发布失败数 | number | 中间件写入 | 表5 发布状态=发布失败 count |
| 待发布数 | number | 中间件写入 | 表5 发布状态∈{待发布,发布中} count |
| 最新发布时间 | datetime | 中间件写入 | 表5 MAX(实际发布时间) |
| 最新发布内容 | text | 中间件写入 | 最近一次发布编号 |
| ID | auto_number | 系统自动 | 只读 |

### 实施步骤

| 步骤 | 内容 | 状态 |
|------|------|------|
| Step 1 | lark-cli 建表 + 全部字段 | ✅ |
| Step 2 | `system.yaml` 新增 `tables.sku_stats: tblJRHExnxytve7s` | ✅ |
| Step 3 | 为现有 2 个 SKU 各创建初始化行（数字字段全 0） | ✅ |
| Step 4 | `publish.py` 新增 `_update_sku_stats(pub_record_id)` | ✅ |

### 初始化数据

| record_id | SKU编号 | SKU名称 |
|-----------|---------|---------|
| recvgapsm9V5Su | SKU_002 | 【月光白】亲肤质感-强磁吸 |
| recvgapuAIijzO | SKU_001 | 【炫酷黑】亲肤质感-强磁吸 |

### `_update_sku_stats()` 逻辑

```
pub_record → 关联内容 → 关联SKU
→ 列出该SKU所有内容记录（累计生成内容数）
→ 列出所有内容对应的发布记录
→ 按发布状态 COUNT（成功/失败/待发布）
→ 取 MAX(实际发布时间) + 最新发布编号
→ update_record 写入统计表对应行
```

**触发时机**：publish.py 发布成功 OR 发布失败后各调用一次

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `middleware/adapters/feishu.py` | 新增方法 | `send_group_text()` + `send_group_card()` |
| `middleware/config/system.yaml` | 新增配置 | `notifications` 块 + `tables.sku_stats` |
| `middleware/handlers/publish.py` | 新增方法+调用 | `_notify_card_success()`, `_notify_card_failure()`, `_update_sku_stats()`, `_get_sku_stats_summary()` |
| `middleware/handlers/publish_record_creator.py` | 新增方法+调用 | `_notify_card_queued()`，创建记录后调用 |
| `middleware/main.py` | 参数透传 | `notifications_cfg` 传给2个handler |
| `middleware/test_notify.py` | 新增 | 三种状态卡片手动测试脚本 |
| **飞书 Base** | 新建表+字段+数据 | SKU发布统计表，2条初始行 |

---

## 验证结果

- ✅ 三种状态卡片（蓝/绿/红）手动发送验证通过（2026-04-08）
- ✅ 通知失败不影响主流程（所有通知方法静默处理异常）
- [ ] 触发真实发布，端到端验证卡片 + SKU统计表联动更新
