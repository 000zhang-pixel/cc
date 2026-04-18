# Prompt 系统升级 v2：最新更新评估与针对性建议

> 评估时间：2026-04-18  
> 评估对象：最新 `origin/main`（HEAD: `0287e75`）  
> 上轮参考：`docs/reviews/prompt-upgrade-v2-round2-review-2026-04-18.md`、`docs/reviews/prompt-upgrade-v2-round2-implementation-2026-04-18.md`  
> 本轮重点：拉取最新代码后，对补强实现做二次审阅、验证与定向建议

---

## 1. 结论摘要

本轮更新是**有效补强**，且已经把上一轮 review 中的大部分高优先级问题推进到了“可用 / 可回归”状态。

当前可以确认：
- `scene_variety=高` 的小场景池退化问题已修复
- `diff_strength=低` 已从“几乎无差异”调整为“弱差异”
- Persona 分配已从“优先级轮转”升级为“软匹配 + 去重优先”
- `setup_v2_schema.py` 的路径与 seed 健壮性已增强
- 表4 已支持 `图片生成调试信息` 摘要写入
- 本地静态检查与新增 3 个验证脚本均通过

综合判断：

**Prompt v2 主链路目前已基本闭环，可以进入“小范围真实样本回归 + 最后一轮匹配完善”阶段。**

但需要明确：

**当前版本还不应宣称“PRD 协同匹配全部完成”，因为 `strategy→persona` 和 `persona→scene` 两个标签维度仍未真正接入生产评分逻辑。**

---

## 2. 本轮已确认的有效改进

## 2.1 `scene_variety=高` 小 pool 退化问题已实质修复

### 代码事实
`_assign_scenes()` 不再使用固定 `step=2` 轮转，而是改为：
- 当 `pool >= groups`：按偏移顺序取唯一 scene
- 当 `pool < groups`：每一轮复制 `pool` 后重新 shuffle，再拼接到序列中

对应逻辑位于：
- `middleware/handlers/content_generation.py`

### 验证事实
已运行：

```bash
cd /Users/carson/workspace/ai-content-hub/middleware
python3 scripts/validate_scene_variety.py
```

结果通过，关键回归场景包括：
- `pool=2, groups=3, variety=高` → `avg_unique=66.7%`
- `pool=2, groups=4, variety=高` → `avg_unique=50.0%`
- `pool=4, groups=3, variety=高` → `avg_unique=100.0%`

### 评估
这是本轮最明确的边界修复之一，旧问题已不再存在。

---

## 2.2 `diff_strength=低` 已改为“弱差异”而非“零差异”

### 代码事实
`_build_creative_briefs()` 现按维度分别控制轮转：
- `低`：title 轮转，narrative / structure 固定
- `中`：title / narrative / structure 全部 step=1
- `高`：title / narrative / structure 全部 step=2

### 验证事实
已运行：

```bash
cd /Users/carson/workspace/ai-content-hub/middleware
python3 scripts/validate_diff_strength.py
```

结果：
- `低`：唯一标题 `3`，唯一叙事 `1`，唯一结构 `1`
- `中`：唯一标题 `3`，唯一叙事 `3`，唯一结构 `3`
- `高`：唯一标题 `3`，唯一叙事 `3`，唯一结构 `3`

### 评估
这次定义更符合业务语义：
- 保持“低差异化”的整体一致感
- 避免出现“三组标题完全相同”的质量回退

---

## 2.3 Persona 分配已升级为“软匹配 + 批内去重优先”

### 代码事实
`_assign_personas()` 中新增 `_soft_score()`，当前评分已包含：
- `适用内容类型` 命中
- `scene.适合人设标签` 与 `persona.气质标签` 的交集数量
- `优先级` 作为微权重 tiebreaker

同时：
- `固定主人设`：选全组聚合得分最高的人设
- `自动 / 多人设轮换`：单组选最优，并优先避免批内重复

### 验证事实
已运行：

```bash
cd /Users/carson/workspace/ai-content-hub/middleware
python3 scripts/validate_persona_path.py
```

结果通过，覆盖：
- Persona 表存在路径
- Persona 表缺失 fallback 路径
- 固定主人设路径
- 内容类型软匹配路径

### 评估
这说明人设链路不再只是“按优先级循环发牌”，而是开始具备配置驱动的匹配能力。

---

## 2.4 Scene dict 已补足 v2 需要的关键字段

### 代码事实
`_assign_scenes()` 返回的 scene dict 已新增：
- `道具建议`
- `适合人设标签`

### 评估
这两个字段的补入是正确的：
- `道具建议` 让 prompt builder 的 `.get()` 不再永远为空
- `适合人设标签` 让场景到人设的软匹配成为可能

---

## 2.5 表4 图片调试摘要已进入业务可见层

### 代码事实
图片生成后，`_generate_content()` 会向更新字段中写入：
- `图片生成调试信息`

内容为摘要版：
- 失败数量
- 失败序号
- Prompt 前 120 字摘要

### 评估
这是实用增强。
运营无需查看本地 debug 文件，也能在飞书表中快速判断异常情况。

---

## 2.6 `setup_v2_schema.py` 工程健壮性有明显提升

### 已确认改动
- `system.yaml` 写回路径已改为 repo-relative
- 当表12已存在但为空时，会自动 seed Persona 初始数据
- `TABLE4_FIELDS` 已新增 `图片生成调试信息`

### 评估
这部分已经从“环境依赖强、容易半完成”升级为“更可复用的维护脚本”。

---

## 3. 本轮仍存在的问题

## Important

### 3.1 `strategy→persona` 与 `persona→scene` 的标签匹配仍未真正进入生产逻辑

### 检索事实
在 `middleware/handlers/content_generation.py` 中检索结果为：
- `人设适配标签` → 0 次命中
- `适合场景标签` → 0 次命中
- `适合人设标签` → 已使用

### 含义
当前已落地的软匹配只覆盖了：
- 内容类型匹配
- scene 标签 → persona 气质标签 匹配
- priority 微权重

但仍未覆盖：
- strategy `人设适配标签`
- persona `适合场景标签`

### 影响
当前系统已经明显优于旧轮转逻辑，但仍未完全达到 PRD 中“策略 / 场景 / 人设协同软匹配”的目标。

### 建议
建议作为下一优先级补齐以下两项加权：
1. `strategy.人设适配标签 ∩ persona 标签`
2. `persona.适合场景标签 ∩ scene 场景标签`

建议采用最小加权增量接入，不做大重构。

---

### 3.2 当前验证脚本是“逻辑镜像验证”，不是“真实函数回归验证”

### 事实
新增的 3 个脚本都采用本地模拟方式：
- 重建轮转或评分逻辑
- 断言模拟输出

它们**没有直接实例化并调用** `ContentGenerationHandler` 的真实方法。

### 风险
若后续生产代码与脚本实现发生偏移，可能出现：
- 脚本仍然通过
- 真实逻辑已经偏离

### 建议
至少新增一层“真实函数级”回归测试：
- mock `_feishu`
- mock `_storage`
- 直接调用 `_assign_scenes()` / `_assign_personas()` / `_build_creative_briefs()`

这能显著提高验证可信度。

---

## Minor

### 3.3 Persona 去重当前依赖 `id(r)`，语义上不如 `record_id` 清晰

### 事实
自动分配时通过 `id(r)` 跟踪已使用 persona。

### 风险
当前实现能工作，但工程语义不够稳定、也不够直观。

### 建议
改为使用 `record_id` 去重：
- 更易读
- 更符合业务对象标识
- 更不依赖 Python 对象身份

---

### 3.4 `setup_v2_schema.py` 写回 `system.yaml` 仍基于字符串替换，长期维护性一般

### 事实
当前写回仍依赖：

```python
content = content.replace('persona:      ""', f'persona:      {persona_table_id}')
```

### 风险
如果 YAML 空格、引号格式调整，这段逻辑可能失效。

### 建议
若该脚本将持续维护，建议后续改为 YAML 解析后写回，而不是字符串替换。

---

## 4. 本轮验证记录

已执行：

```bash
cd /Users/carson/workspace/ai-content-hub
git pull --ff-only origin main
python3 -m py_compile middleware/handlers/content_generation.py \
  middleware/scripts/setup_v2_schema.py \
  middleware/scripts/validate_scene_variety.py \
  middleware/scripts/validate_diff_strength.py \
  middleware/scripts/validate_persona_path.py

cd /Users/carson/workspace/ai-content-hub/middleware
python3 scripts/validate_scene_variety.py
python3 scripts/validate_diff_strength.py
python3 scripts/validate_persona_path.py
```

结果：
- `git pull` ✅
- `py_compile` ✅
- `validate_scene_variety.py` ✅
- `validate_diff_strength.py` ✅
- `validate_persona_path.py` ✅

说明：
- 本轮结论基于代码审阅 + git diff + 本地静态检查 + 本地验证脚本
- 未在本机重新执行真实 Feishu schema 迁移
- 未在本机重跑真实样本生成回归

---

## 5. 综合结论

### 已达到
- Prompt v2 主链路基本闭环
- 关键边界问题已有明确修复
- 工程可观测性与 schema 健壮性明显提升
- 已具备进入真实样本回归的条件

### 尚未完全达到
- PRD 级别的完整三方协同匹配仍未全量落地
- 测试仍偏“模拟验证”，缺少真实函数回归层

### 工程判断
**当前版本可以视为“可用且值得继续收口”的版本，不建议再做大范围架构改造；建议转入“小步补齐匹配维度 + 增加真实函数测试 + 做一轮真实样本回归”的收尾阶段。**

---

## 6. 针对性建议（按优先级）

### 第一优先级
1. 把 `strategy.人设适配标签` 与 `persona.适合场景标签` 接入 Persona 评分
2. 增加直接调用 `ContentGenerationHandler` 的函数级回归测试

### 第二优先级
3. 将 Persona 去重从 `id(r)` 改为 `record_id`
4. 将 `system.yaml` 写回从字符串替换升级为 YAML 读写

### 第三优先级
5. 做一次真实样本回归，重点验证：
   - 3 组标题是否足够分散
   - 叙事角度是否符合 `diff_strength` 预期
   - 同组 5 图人物一致性是否稳定
   - Persona soft-match 是否明显优于旧轮转逻辑

---

## 7. 建议给执行端的下一步任务定义

可直接转发：

> 请基于 `docs/reviews/prompt-upgrade-v2-latest-review-2026-04-18.md` 继续执行 Prompt 系统升级 v2 的最后一轮收口。  
> 当前目标不是重构，而是补齐协同匹配与提高验证可信度。  
> 请优先处理：  
> 1. 将 `strategy.人设适配标签` 接入 Persona 评分；  
> 2. 将 `persona.适合场景标签` 接入 Persona 评分；  
> 3. 增加直接调用 `ContentGenerationHandler` 的函数级回归测试；  
> 4. 将 Persona 去重逻辑从 `id(r)` 改为 `record_id`；  
> 5. 若改动 `setup_v2_schema.py`，优先改进 YAML 写回健壮性。  
> 每项改动都必须附带：改动文件、关键 diff、验证命令、验证结果、残余风险。  
> 若飞书字段缺失，仍必须 fallback，不得阻断旧任务。
