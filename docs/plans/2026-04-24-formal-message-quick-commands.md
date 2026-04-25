# Formal Message Quick Commands

## short
- `受理 short` → `受理 ... --format interactive --detail-level short`
- `接单 short` → `接单 ... --format interactive --detail-level short`
- `进展 short` → `进展 ... --format interactive --detail-level short`
- `风险 short` → `风险 ... --format interactive --detail-level short`
- `催办 short` → `催办 ... --format interactive --detail-level short`
- `结论 short` → `结论 ... --format interactive --detail-level short`

## standard
- `派单` → `派单 ... --format interactive`
- `风险` → `风险 ... --format interactive`
- `结论` → `结论 ... --format interactive`
- `仲裁` → `仲裁 ... --format interactive`

## rich
- `派单 rich` → `派单 ... --format interactive --detail-level rich --annex-link ...`
- `进展 rich` → `进展 ... --format interactive --detail-level rich --annex-link ...`
- `交付 rich` → `交付 ... --format interactive --detail-level rich --annex-link ...`

## 角色参数速记
- 协作人：`--collaborator`
- 下一责任人：`--next-owner`
- 收口抄送：`--closer`
- 决策人：`--decision-maker`

## 判断口诀
- 先立状态 → `short`
- 常规协同 → `standard`
- 细节很多 → `rich`

## Smart hints 速记
- 看 `recommended_detail_level`
- 看 `warnings`
- 看 `suggestions`
- 看 `violations`
- annex 不匹配时优先修正
- 角色参数传了但模板没占位时必须改模板或换层级
- 要强约束时加 `--strict-hints`，违规直接 exit 2

## 业务区块传参
- 正式推荐：在 `--data` 中传 `actions[]`、`guardrails[]`
- dispatch：`actions[]` 表示回报格式；`guardrails[]` 表示禁止项
- risk / arbitration：`actions[]` 表示需要动作 / 后续动作；`guardrails[]` 表示边界提醒
- 旧字段 `report_item_* / action_item_* / guardrail_*` 仍短期兼容，但 wrapper 会给出 warning，不建议继续新增使用

## 每日工作规划 / 工作总结快捷入口
- 规范文档：`docs/plans/2026-04-25-multi-agent-daily-plan-and-summary-template-standard.md`
- 一键命令：`docs/plans/2026-04-25-daily-plan-summary-quick-commands.md`
- 默认口径：
  - 每日工作规划 → `【进展】 rich`
  - 每日工作总结 → `【结论】 standard`
- 对应示例：
  - CEO 工作规划：`middleware/templates/feishu_interactive_render_example_progress_daily_plan_ceo.json`
  - 技术工作规划：`middleware/templates/feishu_interactive_render_example_progress_daily_plan_it_agent.json`
  - 内容工作规划：`middleware/templates/feishu_interactive_render_example_progress_daily_plan_cc_agent.json`
  - CEO 工作总结：`middleware/templates/feishu_interactive_render_example_conclusion_daily_summary_ceo.json`
  - 技术工作总结：`middleware/templates/feishu_interactive_render_example_conclusion_daily_summary_it_agent.json`
  - 内容工作总结：`middleware/templates/feishu_interactive_render_example_conclusion_daily_summary_cc_agent.json`
- 注意：`progress rich` 工作规划命令不要传 `--closer`；`conclusion standard` 工作总结可传 `--closer Hermes_CEO`

## strict smoke
- 全量：`python3 middleware/scripts/feishu_formal_message_strict_smoke.py`
- 列 case：`python3 middleware/scripts/feishu_formal_message_strict_smoke.py --list`
- 跑单 case：`python3 middleware/scripts/feishu_formal_message_strict_smoke.py --case dispatch_annex_mismatch_blocked`
