# 爆款素材分析与批量学习 — 设计文档

**日期**：2026-04-05  
**状态**：待实现  
**关联表**：表6（素材知识库）、表8（Strategy）、表9（ShotPlan）、表10（Scene）

---

## 一、背景与目标

现有 `MaterialAnalysisHandler` 已完成文本 AI 分析，但图片视觉分析为空占位符（placeholder）。  
分析结果停留在表6，未与 Prompt 引擎形成闭环。

**本次目标**：
1. **补全图片视觉分析**：实现 `_analyze_image_placeholder` → 真实图片分析
2. **批量学习闭环**：手动运行脚本，AI 汇总多条爆款数据 → 在引擎表（8/9/10）创建新记录

---

## 二、功能一：图片视觉分析

### 2.1 数据流

```
MaterialAnalysisHandler._run()
  ├── _detect_platform(url)            # 已有
  ├── _analyze_text(adapter, ...)      # 已有，文本分析
  ├── _download_attachment(rec)        # 新增：从飞书下载附件 → bytes | None
  ├── _analyze_image(vision, bytes)    # 新增：视觉模型分析 → dict
  └── update_record(table6, fields)   # 写回构图风格/色调氛围/场景道具
```

### 2.2 飞书附件下载

**新增** `FeishuClient.download_attachment(file_token: str) -> bytes`

```
GET https://open.feishu.cn/open-apis/drive/v1/medias/{file_token}/download
Authorization: Bearer {tenant_access_token}
```

返回原始图片字节（JPEG/PNG）。失败时 raise，调用方 catch 后跳过图片分析（不影响文本分析结果）。

### 2.3 视觉模型适配器

**新增** `VisionModelAdapter`（`middleware/adapters/ai_models.py`）：

- 使用 OpenAI-compatible API，支持 messages 中携带 base64 图片
- 配置：`model_params.yaml` 新增 `vision_model` 节，provider 使用 Kimi vision 模型（`moonshot-v1-8k-vision`，共用 `KIMI_API_KEY`）
- 接口：`analyze(system, user, image_bytes: bytes) -> str`
  - 将 image_bytes 转为 `data:image/jpeg;base64,...` 嵌入 user messages
  - 返回 AI 文本回复

**新增** `build_vision_adapter(model_params) -> VisionModelAdapter`（工厂函数）

### 2.4 图片分析 Prompt

```
System: 你是一名电商内容视觉分析专家。请严格按 JSON 格式输出，不要有其他文字。

User: 请分析这张电商种草内容的截图，输出 JSON：
{
  "composition": "构图风格，如：平铺/斜角/场景融入/特写",
  "tone": "色调氛围，如：明亮清新/暗调高级/粉嫩少女/自然原木",
  "props": "场景与道具描述，简洁一句话"
}
```

失败（无附件 / API 报错）时静默跳过，三个字段留空（与现有 placeholder 行为一致）。

### 2.5 改动范围

| 文件 | 改动内容 |
|------|---------|
| `middleware/adapters/feishu.py` | 新增 `download_attachment(file_token)` |
| `middleware/adapters/ai_models.py` | 新增 `VisionModelAdapter`、`build_vision_adapter()` |
| `middleware/config/model_params.yaml` | 新增 `vision_model` 节（Kimi vision provider） |
| `middleware/handlers/material_analysis.py` | 实现 `_download_attachment()`、`_analyze_image()`，替换 placeholder |
| `middleware/main.py` | 构建 VisionModelAdapter 并注入 MaterialAnalysisHandler |

---

## 三、功能二：批量学习脚本

### 3.1 触发方式

手动运行：
```bash
cd d:/claude_code
python scripts/batch_learn.py
```

无需飞书触发字段，无需修改 Poller。脚本独立运行，读取 `.env` + middleware config。

### 3.2 整体流程

```
① 读取表6所有「分析状态=已完成」记录（至少需要 3 条，否则提示不足并退出）
② 构建跨记录汇总结构：
     - 文案维度：品类分布、内容类型分布、高频标题公式、高频正文结构、情绪触发点组合
     - 视觉维度：构图风格、色调氛围、场景道具（仅有附件分析的记录）
③ 一次 AI 调用 → 合成新引擎记录 JSON
④ 写入引擎表（表8/9/10），新记录均为「停用」状态
⑤ 去重：(适用品类, 切入角度, 情绪基调) 全相同则跳过不重复建
⑥ 输出报告：新建 X 条 Strategy / Y 条 ShotPlan / Z 条 Scene，跳过 W 条（重复）
```

### 3.3 AI Prompt 设计

输入给 AI 的汇总结构（文本格式）：

```
以下是 N 条爆款内容的分析摘要，请提炼规律并输出引擎记录。

--- 爆款摘要 ---
[1] 品类:手机壳 | 内容类型:种草推荐 | 标题公式:数字列表 | 正文结构:场景带入→产品→效果 | 情绪:共鸣,焦虑 | 卖点:场景型 | 构图:平铺 | 色调:明亮清新
[2] ...
[N] ...

请输出 JSON：
{
  "strategies": [
    {
      "策略名称": "...",
      "切入角度": "精致生活|学生平价|极限测评|社交货币|实用主义|情感共鸣",
      "情绪基调": "松弛感|兴奋感|专业理性|温暖亲密|高冷极简|活泼俏皮",
      "表达方式": "生活记录感种草|干货测评|朋友推荐|场景故事|对比揭秘|教程攻略",
      "系统提示词前缀": "你是一名...",
      "文案叙事节点": [{"index":1,"zh":"节点名","guidance":"写作指引"},...],
      "适用内容类型": ["种草推荐"],
      "适用平台": ["小红书"],
      "适用品类": ["手机壳"]
    }
  ],
  "shotplans": [
    {
      "方案名称": "...",
      "适用内容形态": ["图片生成"],
      "适用内容类型": ["种草推荐"],
      "适用品类": ["手机壳"],
      "角色序列": [{"index":1,"en":"Shot description with {scene_description}"},...],
      "节点数量": 4
    }
  ],
  "scenes": [
    {
      "场景名称": "...",
      "适用品类": ["手机壳"],
      "适用平台": ["小红书"],
      "场景基底_英文": "English scene base description...",
      "风格基调词": "warm, bright, lifestyle",
      "排除描述": "avoid dark, messy...",
      "场景描述_中文": "中文场景描述",
      "权重": 5
    }
  ]
}
```

### 3.4 新记录字段规范

**Strategy（表8）**：
- 策略编号：留空（飞书自动或人工填）
- 是否启用：`停用`
- 优先级：`5`
- 备注：`来源：爆款批量学习 {YYYY-MM-DD}，基于 {N} 条爆款`

**ShotPlan（表9）**：
- 方案编号：留空
- 是否启用：`停用`
- 节点数量：由 AI 输出的角色序列数组长度确定
- 备注：`来源：爆款批量学习 {YYYY-MM-DD}`

**Scene（表10）**：
- 场景编号：留空
- 是否启用：`停用`
- 权重：`5`（人工审核后可调整）
- 其余结构字段（人物/环境/光线/构图模块）：暂不填，专注 NANOBANANA 核心块
- 备注：`来源：爆款批量学习 {YYYY-MM-DD}`

### 3.5 去重规则

| 表 | 去重 key |
|----|---------|
| 表8 Strategy | (适用品类集合, 切入角度, 情绪基调) 全相同 |
| 表9 ShotPlan | (适用品类集合, 适用内容形态集合) 全相同 |
| 表10 Scene | 场景名称完全相同 |

### 3.6 脚本结构

```
scripts/batch_learn.py
  main()
    ├── load .env + middleware config (reuse core/config.py)
    ├── FeishuClient(...)
    ├── build_text_adapter(...)   # 复用已有工厂
    ├── fetch_completed_materials()  → list[dict]
    ├── build_summary(records)       → str（汇总文本）
    ├── call_ai(adapter, summary)    → dict（parsed JSON）
    ├── fetch_existing_engine_records()  → {strategies, shotplans, scenes}
    ├── write_strategies(new, existing)
    ├── write_shotplans(new, existing)
    ├── write_scenes(new, existing)
    └── print_report(created, skipped)
```

脚本通过 `sys.path.insert(0, "middleware")` 复用 middleware 的 FeishuClient 和 TextModelAdapter，**不引入新依赖**。

---

## 四、错误处理

| 场景 | 处理方式 |
|------|---------|
| 附件下载失败 | 跳过图片分析，文本分析结果照常写回 |
| 视觉 AI 调用失败 | 三个视觉字段留空，`分析状态=已完成` 正常写回 |
| batch_learn：记录数 < 3 | 打印警告并退出，不调用 AI |
| batch_learn：AI 返回 JSON 解析失败 | 打印原始 AI 输出并退出，不写入飞书 |
| batch_learn：单条记录写入失败 | 打印错误继续写其余记录 |

---

## 五、不在本次范围

- 标签推荐（表7自动写入）：用户确认不做，表7由人工维护
- 表6新增字段：本次不改表结构
- 图片下载后本地缓存：直接在内存处理，不落盘
- 单条爆款分析完自动更新引擎表：不做，只做手动批量触发
