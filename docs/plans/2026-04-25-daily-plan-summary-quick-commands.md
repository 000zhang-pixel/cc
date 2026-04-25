# 每日工作规划 / 工作总结快捷命令

> 统一入口：`middleware/scripts/feishu_formal_message.py`
>
> 推荐口径：
> - **每日工作规划** → 正式 `【进展】 rich`
> - **每日工作总结** → 正式 `【结论】 standard`
>
> 模板规范文档：
> `docs/plans/2026-04-25-multi-agent-daily-plan-and-summary-template-standard.md`

---

## 1. 每日工作规划（`【进展】 rich`）

### Hermes_CEO
```bash
python3 middleware/scripts/feishu_formal_message.py \
  进展 Hermes_CEO \
  --format interactive \
  --detail-level rich \
  --data middleware/templates/feishu_interactive_render_example_progress_daily_plan_ceo.json \
  --identity default_app \
  --chat hermes_board
```

### 大T_技术总工
```bash
python3 middleware/scripts/feishu_formal_message.py \
  进展 大T_技术总工 \
  --format interactive \
  --detail-level rich \
  --data middleware/templates/feishu_interactive_render_example_progress_daily_plan_it_agent.json \
  --identity default_app \
  --chat hermes_board
```

### 大C_内容总监
```bash
python3 middleware/scripts/feishu_formal_message.py \
  进展 大C_内容总监 \
  --format interactive \
  --detail-level rich \
  --data middleware/templates/feishu_interactive_render_example_progress_daily_plan_cc_agent.json \
  --identity default_app \
  --chat hermes_board
```

---

## 2. 每日工作总结（`【结论】 standard`）

### Hermes_CEO
```bash
python3 middleware/scripts/feishu_formal_message.py \
  结论 Hermes_CEO \
  --format interactive \
  --data middleware/templates/feishu_interactive_render_example_conclusion_daily_summary_ceo.json \
  --identity default_app \
  --chat hermes_board \
  --closer Hermes_CEO
```

### 大T_技术总工
```bash
python3 middleware/scripts/feishu_formal_message.py \
  结论 大T_技术总工 \
  --format interactive \
  --data middleware/templates/feishu_interactive_render_example_conclusion_daily_summary_it_agent.json \
  --identity default_app \
  --chat hermes_board \
  --closer Hermes_CEO
```

### 大C_内容总监
```bash
python3 middleware/scripts/feishu_formal_message.py \
  结论 大C_内容总监 \
  --format interactive \
  --data middleware/templates/feishu_interactive_render_example_conclusion_daily_summary_cc_agent.json \
  --identity default_app \
  --chat hermes_board \
  --closer Hermes_CEO
```

---

## 3. 使用边界

1. **工作规划**优先用 `【进展】 rich`，因为它更适合承载：
   - 当前主线
   - 已完成前置梳理
   - 今日待推进动作
   - 节奏与下一节点
   - 附录链接

2. **工作总结**优先用 `【结论】 standard`，因为它更适合承载：
   - 今日阶段判断
   - 已完成情况
   - 未完成项的后续动作
   - 明日承接口径

3. 若只是非常轻量的日常同步，可降级为 `〔同步〕`，但不建议用碎片短句替代完整规划/总结。

4. 若消息要成立正式责任、正式交付、正式催办或正式仲裁，仍需使用对应正式标签，不要拿工作规划/总结卡替代。

---

## 4. 推荐改法

最常改的字段：
- `task_name`
- `goal`
- `todo_done_* / todo_pending_*`
- `judgement_*`
- `status`
- `deadline`
- `next_milestone`
- `annex_title / annex_summary / annex_link`

推荐做法：
- 先复制最接近角色的 example json
- 改完后先 `--dry-run`
- 确认内容、mentions、receipt 口径无误后再正式发群
