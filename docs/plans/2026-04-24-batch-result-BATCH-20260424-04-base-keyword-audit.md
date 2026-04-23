# BATCH-20260424-04 Base 关键词审计结果单

- 批次：BATCH-20260424-04
- 日期：2026-04-24
- 范围：Feishu Base 高优先表与关联表关键词审计
- 关键词：`校园` / `图书馆` / `旅行` / `新年礼物` / `数码礼物`
- 模式：只读审计
- dry-run：通过（本次为只读扫描，无写操作）
- apply：未执行
- 涉及代码改动：无（本批次仅执行线上 Base 审计；本轮之前已完成 formal next-owner mention 修复，不计入本结果单）

## 1. 审计结论摘要

### 1.1 高优先表

| 表 | table_id | record_count | hit_count | 结论 |
|---|---|---:|---:|---|
| prompt | tbljMPKdYbGTb1K7 | 57 | 5 | 存在跨场景残留词，集中在 `子Prompt列表 / 创意包 / 总Prompt` |
| content | tblieT8ZK8HOQt0x | 47 | 25 | 问题最集中，主要在 `标签`，少量在 `正文` |
| tag | tblsnxUwqY1WgEAQ | 124 | 2 | 命中基础标签词本身：`#新年礼物`、`#数码礼物` |

### 1.2 关联表

| 表 | table_id | record_count | hit_count | 结论 |
|---|---|---:|---:|---|
| strategy | tblu2EzR78tWjYf6 | 44 | 1 | 存在明显校园学习策略条目 |
| scene | tbliWlwiyA4sppgY | 121 | 7 | 存在校园/图书馆/旅行相关场景 |
| persona | tblxSbOoZ2kMCkc6 | 26 | 5 | 存在校园/图书馆方向 persona |
| shotplan | tbl0xCaqru1TjwzK | 52 | 4 | 存在校园/图书馆/旅行方向方案 |
| plan | tblDJ2hCvl7y4x5s | 26 | 0 | 未命中 |

## 2. 关键发现

### 2.1 content 表是当前主问题面

- `content.hit_count = 25 / 47`
- 大部分命中来自 `标签`
- 直接命中的冲突标签包括：
  - `#新年礼物`
  - `#数码礼物`
- 少量正文仍带场景污染词，例如：
  - `校园`
  - `图书馆`

样例：
- `recvh2ql9oqdze`：标签含 `#新年礼物`
- `recvh2sRJPRNvr`：标签含 `#数码礼物`
- `recvh2sXjQJmbe`：标签含 `#新年礼物`，正文含 `校园`
- `recvhiZzAeqzxs`：标签含 `#新年礼物`，正文含 `图书馆`
- `recvhw4xcnNa0C`：标签含 `#新年礼物`，正文含 `图书馆`

### 2.2 prompt 表存在残留 prompt 污染

- `prompt.hit_count = 5 / 57`
- 主要落点：
  - `子Prompt列表`
  - `创意包JSON`
  - `创意包摘要`
  - `总Prompt`

典型残留：
- `校园或图书馆背景`
- `图书馆或书房`
- `旅行穿搭整体亮相`

样例：
- `recvhCIm50rJGA`：`子Prompt列表` 含 `校园 / 图书馆`
- `recvhDOYmzMZ1D`：`子Prompt列表` 含 `校园 / 图书馆`
- `recvhDQjH26yZ4`：`创意包JSON / 创意包摘要 / 子Prompt列表 / 总Prompt` 含 `图书馆`
- `recvhDUcjkSDqz`：`子Prompt列表` 含 `旅行`

### 2.3 tag 表存在上游脏标签源

- `tag.hit_count = 2 / 124`
- 命中：
  - `recvfOSrsjSGhM` → `#新年礼物`
  - `recvfOSshrCzC8` → `#数码礼物`

结论：如果不处理 tag 表源词，仅清 content 表可能会再次回流。

### 2.4 关联表并非全部都应删除，需要区分“业务允许场景”与“当前批次审计范围”

发现：
- strategy/scene/persona/shotplan 中存在校园、图书馆、旅行等结构化条目
- 这些条目本身不一定是“脏数据”
- 但在当前手机壳/手机链审计批次中，若被错误注入到不匹配内容里，就会形成污染

结论：
- `新年礼物 / 数码礼物` 当前更接近“确定性冲突词”
- `校园 / 图书馆 / 旅行` 需区分：
  - 是合法策略/场景库存
  - 还是误注入到当前样本的残留词

## 3. 风险判断

### Critical
1. content 表已有大量线上记录仍带 `#新年礼物 / #数码礼物`
2. prompt 表已有残留场景词写入生成链路产物，后续可能继续污染新内容

### Important
3. tag 表存在上游冲突标签源，若不处理会重复写回 content
4. strategy/scene/persona/shotplan 中存在相关词条，不能直接全量删除，需按“当前批次适配性”治理

### Minor
5. plan 表未命中，说明问题更集中在生成资产与标签链路，不在 plan 主表

## 4. dry-run / apply 判定

- dry-run：已完成（只读扫描）
- apply：未执行

未直接 apply 的原因：
1. `tag` / `content` / `prompt` 涉及线上内容与上游词库，属于真实业务数据
2. `校园 / 图书馆 / 旅行` 并非全部可直接判定为错误，需要区分合法库存与当前批次误注入
3. 直接批量删除存在误伤风险，需先形成字段级修正清单

## 5. 建议的下一批动作

### 5.1 可直接进入修正候选的项（优先）
- tag 表：
  - `#新年礼物`
  - `#数码礼物`
- content 表中标签字段的同名标签

### 5.2 需要二次筛选后再修的项
- prompt/content 中出现的：
  - `校园`
  - `图书馆`
  - `旅行`
- 需要结合当前内容编号、产品、策略、scene/persona/shotplan 判断是否误注入

## 6. 输出物

- 本结果单：`docs/plans/2026-04-24-batch-result-BATCH-20260424-04-base-keyword-audit.md`

## 7. 当前结论

本轮审计已证明：
1. 大C提出的两类问题在 Base 中都真实存在
2. `标签冲突` 当前比 `场景残留词` 更适合先做首批 apply
3. 若要安全推进，推荐下一批改为：
   - 批次 A：先清 `tag/content` 中的 `新年礼物 / 数码礼物`
   - 批次 B：再对 `prompt/content` 中的 `校园 / 图书馆 / 旅行` 做样本级误注入筛选
