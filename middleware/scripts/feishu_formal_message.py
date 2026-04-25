#!/usr/bin/env python3
"""Unified wrapper for formal Feishu messages.

This wrapper reduces the chance of bypassing verified mention send flow.
It can delegate either to text/post verified mention sending or to the
interactive card formal pipeline with a shared receipt shape.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent / "templates"
VERIFIED_SENDER = SCRIPT_DIR / "feishu_verified_mention_send.py"
INTERACTIVE_SENDER = SCRIPT_DIR / "send_formal_interactive_card.py"

PRESET_SUFFIX = {
    "plain": "{text}",
    "eta": "{text} 预计 15 分钟内回传。",
    "blocked": "{text} 当前存在阻塞，请关注后续【风险】同步。",
    "handoff": "{text} 请接续处理，并在完成后回传【交付】。",
}

TEMPLATE_KEYS = {
    "accept": "feishu_interactive_01_accept.json",
    "dispatch": "feishu_interactive_02_dispatch.json",
    "ack": "feishu_interactive_03_ack.json",
    "progress": "feishu_interactive_04_progress.json",
    "risk": "feishu_interactive_05_risk.json",
    "followup": "feishu_interactive_06_followup.json",
    "delivery": "feishu_interactive_07_delivery.json",
    "conclusion": "feishu_interactive_08_conclusion.json",
    "arbitration": "feishu_interactive_09_arbitration.json",
}

TEMPLATE_VARIANTS = {
    "accept": {"short": "feishu_interactive_01_accept_short.json"},
    "dispatch": {"rich": "feishu_interactive_02_dispatch_rich.json"},
    "ack": {"short": "feishu_interactive_03_ack_short.json"},
    "progress": {"short": "feishu_interactive_04_progress_short.json", "rich": "feishu_interactive_04_progress_rich.json"},
    "risk": {"short": "feishu_interactive_05_risk_short.json"},
    "followup": {"short": "feishu_interactive_06_followup_short.json"},
    "delivery": {"rich": "feishu_interactive_07_delivery_rich_final.json"},
    "conclusion": {"short": "feishu_interactive_08_conclusion_short.json"},
}

LABEL_TO_TEMPLATE_KEY = {
    "受理": "accept",
    "派单": "dispatch",
    "接单": "ack",
    "进展": "progress",
    "风险": "risk",
    "催办": "followup",
    "交付": "delivery",
    "结论": "conclusion",
    "仲裁": "arbitration",
}

DETAIL_LEVELS = ["short", "standard", "rich"]
ROLE_PLACEHOLDER_HINTS = {
    "target": "owner_mention",
    "next_owner": "next_owner_mentions",
    "collaborator": "collaborator_mentions",
    "closer": "closer_mentions",
    "decision_maker": "decision_maker_mentions",
}
SHORT_CAPABLE = {key for key, variants in TEMPLATE_VARIANTS.items() if "short" in variants}
RICH_CAPABLE = {key for key, variants in TEMPLATE_VARIANTS.items() if "rich" in variants}
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified formal Feishu message wrapper")
    parser.add_argument("label", help="受理/派单/接单/进展/风险/交付/催办/结论/仲裁")
    parser.add_argument("target", help="primary registry target name, e.g. Hermes_CEO")
    parser.add_argument("text", nargs="?", default="", help="body text after the mention; required in text mode")
    parser.add_argument("--next-owner", action="append", default=[], help="additional target(s) that must be real-mentioned as next owner / handoff target; repeatable")
    parser.add_argument("--chat", default="hermes_board", help="chat key in registry")
    parser.add_argument("--identity", default="it_agent_app", help="sender identity key in registry")
    parser.add_argument(
        "--preset",
        choices=sorted(PRESET_SUFFIX.keys()),
        default="plain",
        help="append a standard suffix to reduce manual wording variance (text mode only)",
    )
    parser.add_argument(
        "--format",
        choices=["auto", "text", "interactive"],
        default="auto",
        help="formal message transport format: auto prefers interactive and only falls back to text when explicitly requested or when no interactive path is available",
    )
    parser.add_argument("--template", help="interactive template file name or absolute path")
    parser.add_argument("--template-key", choices=sorted(TEMPLATE_KEYS.keys()), help="interactive template shortcut key")
    parser.add_argument("--detail-level", choices=DETAIL_LEVELS, default="standard", help="interactive template detail level")
    parser.add_argument("--data", help="interactive field data JSON string or path")
    parser.add_argument("--annex-link", help="rich mode annex link")
    parser.add_argument("--annex-title", help="rich mode annex title")
    parser.add_argument("--annex-summary", help="rich mode annex summary")
    parser.add_argument("--collaborator", action="append", default=[], help="interactive mode collaborator mentions")
    parser.add_argument("--closer", action="append", default=[], help="interactive mode closer/cc mentions")
    parser.add_argument("--decision-maker", action="append", default=[], help="interactive mode decision-maker mentions")
    parser.add_argument("--allow-alias-name", action="store_true", help="allow alias name matching in verification")
    parser.add_argument("--strict-mentions", action="store_true", help="fail when mention verification does not pass")
    parser.add_argument("--strict-hints", action="store_true", help="fail fast when smart hints detect blocking issues such as annex mismatch or missing role placeholders")
    parser.add_argument("--no-smart-hints", action="store_true", help="disable wrapper smart hints in output")
    parser.add_argument("--self-check", action="store_true", help="analyze wrapper inputs only; do not send or dry-run downstream sender")
    parser.add_argument("--dry-run", action="store_true", help="delegate in dry-run mode")
    return parser.parse_args()


def render_text(text: str, preset: str) -> str:
    normalized = text.strip()
    if not normalized:
        raise ValueError("text cannot be empty in text mode")
    return PRESET_SUFFIX[preset].format(text=normalized)


def build_text_command(args: argparse.Namespace) -> list[str]:
    text = render_text(args.text, args.preset)
    cmd = [
        sys.executable,
        str(VERIFIED_SENDER),
        "--label",
        args.label,
        "--target",
        args.target,
        "--text",
        text,
        "--chat",
        args.chat,
        "--identity",
        args.identity,
    ]
    for next_owner in args.next_owner:
        cmd.extend(["--next-owner", next_owner])
    if args.dry_run:
        cmd.append("--dry-run")
    return cmd


def base_template_key_for_args(args: argparse.Namespace) -> str | None:
    if args.template_key:
        return args.template_key
    return LABEL_TO_TEMPLATE_KEY.get(args.label)


def supported_detail_levels(base_key: str | None) -> list[str]:
    if not base_key:
        return []
    levels = ["standard"]
    variants = TEMPLATE_VARIANTS.get(base_key) or {}
    for level in DETAIL_LEVELS:
        if level in variants and level not in levels:
            levels.append(level)
    return levels


def variant_template_name(base_key: str, detail_level: str) -> str:
    if detail_level == "standard":
        return TEMPLATE_KEYS[base_key]
    variant = (TEMPLATE_VARIANTS.get(base_key) or {}).get(detail_level)
    if variant:
        return variant
    raise ValueError(f"template_key={base_key!r} does not support detail_level={detail_level!r}")


def resolve_template_path(raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.exists():
        return candidate
    candidate = TEMPLATE_DIR / raw
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Template not found: {raw}")


def load_template_payload(raw: str) -> dict[str, Any]:
    return json.loads(resolve_template_path(raw).read_text())


def resolve_interactive_template(args: argparse.Namespace) -> tuple[str, str | None]:
    if args.template and args.template_key:
        raise ValueError("use either --template or --template-key, not both")
    if args.template:
        return args.template, args.template_key
    base_key = base_template_key_for_args(args)
    if base_key:
        return variant_template_name(base_key, args.detail_level), base_key
    raise ValueError("interactive mode requires --template, --template-key, or a supported label auto-mapping")


def load_json_input(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(raw)
    try:
        candidate = Path(raw)
        if candidate.exists():
            return json.loads(candidate.read_text())
    except OSError:
        pass
    return json.loads(raw)


def merge_interactive_data(args: argparse.Namespace) -> dict[str, Any]:
    data = load_json_input(args.data)
    if args.annex_link:
        data["annex_link"] = args.annex_link
    if args.annex_title:
        data["annex_title"] = args.annex_title
    if args.annex_summary:
        data["annex_summary"] = args.annex_summary
    return data


def maybe_build_interactive_data_file(data: dict[str, Any], original_raw: str | None) -> str | None:
    if not data:
        return original_raw
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", prefix="formal_message_", delete=False)
    with tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
    return tmp.name


def count_populated_fields(data: dict[str, Any]) -> int:
    total = 0
    for value in data.values():
        if value in (None, "", [], {}):
            continue
        total += 1
    return total


def text_burden(data: dict[str, Any]) -> int:
    total = 0
    for value in data.values():
        if isinstance(value, str):
            total += len(value)
        elif isinstance(value, list):
            total += sum(len(str(item)) for item in value)
        elif isinstance(value, dict):
            total += sum(len(str(v)) for v in value.values())
        elif value not in (None, ""):
            total += len(str(value))
    return total


def compute_recommended_detail_level(base_key: str | None, data: dict[str, Any], args: argparse.Namespace) -> tuple[str | None, list[str]]:
    reasons: list[str] = []
    if not base_key:
        return None, reasons
    populated = count_populated_fields(data)
    burden = text_burden(data)
    rich_signals = 0
    short_signals = 0

    deliverable_keys = sorted(key for key in data if key.startswith("deliverable_") and data.get(key) not in (None, "", "-"))
    long_text_keys = [key for key, value in data.items() if isinstance(value, str) and len(value.strip()) >= 90]

    if args.annex_link:
        rich_signals += 2
        reasons.append("检测到 annex_link，说明存在附录入口")
    if args.annex_title or args.annex_summary:
        rich_signals += 1
        reasons.append("检测到 annex 标题/摘要")
    if len(deliverable_keys) >= 3 and args.label in {"派单", "交付", "风险"}:
        rich_signals += 1
        reasons.append("存在多条核心交付项")
    if populated >= 10:
        rich_signals += 1
        reasons.append(f"字段数较多（{populated}）")
    if burden >= 260:
        rich_signals += 1
        reasons.append(f"文本载荷偏高（约 {burden} 字符）")
    if long_text_keys:
        rich_signals += 1
        reasons.append(f"存在较长文本字段：{', '.join(long_text_keys[:3])}")

    if args.label in {"受理", "接单", "进展", "风险", "催办", "结论"} and not args.annex_link:
        if populated <= 6:
            short_signals += 1
        if burden <= 160:
            short_signals += 1
        if len(deliverable_keys) <= 2:
            short_signals += 1

    if base_key in RICH_CAPABLE and rich_signals >= 2:
        return "rich", reasons
    if base_key in SHORT_CAPABLE and short_signals >= 2 and rich_signals == 0:
        if args.label in {"受理", "接单", "进展", "风险", "催办", "结论"}:
            reasons.append("字段较少且文本较轻，适合先用 short 立状态")
            return "short", reasons
    if args.label in {"派单", "交付"} and base_key in RICH_CAPABLE and rich_signals >= 1:
        return "rich", reasons
    return "standard", reasons


def collect_placeholders(node: Any, placeholders: set[str]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            collect_placeholders(value, placeholders)
    elif isinstance(node, list):
        for value in node:
            collect_placeholders(value, placeholders)
    elif isinstance(node, str):
        placeholders.update(PLACEHOLDER_RE.findall(node))


def normalize_section_items(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def collect_legacy_numbered_values(data: dict[str, Any], prefix: str) -> list[str]:
    pairs: list[tuple[int, str]] = []
    for key, value in data.items():
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix):]
        if not suffix.isdigit():
            continue
        text = str(value).strip()
        if not text or text == "-":
            continue
        pairs.append((int(suffix), text))
    return [text for _, text in sorted(pairs)]


def business_sections(template_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sections = template_payload.get("business_sections") or {}
    return sections if isinstance(sections, dict) else {}


def business_field_status(template_payload: dict[str, Any], data: dict[str, Any]) -> dict[str, list[str]]:
    user_provided: list[str] = []
    missing: list[str] = []
    legacy_compat_used: dict[str, list[str]] = {}
    render_keys_generated: list[str] = []
    expected = sorted(business_sections(template_payload).keys())
    for section_name, cfg in business_sections(template_payload).items():
        if not isinstance(cfg, dict):
            continue
        render_key = cfg.get("render_key") or f"{section_name}_md"
        legacy_prefix = cfg.get("legacy_prefix")
        required = bool(cfg.get("required"))
        items = normalize_section_items(data.get(section_name))
        if items:
            user_provided.append(section_name)
            render_keys_generated.append(render_key)
            continue
        if legacy_prefix:
            legacy_items = collect_legacy_numbered_values(data, legacy_prefix)
            if legacy_items:
                legacy_compat_used[section_name] = [f"{legacy_prefix}{idx}" for idx in range(1, len(legacy_items) + 1)]
                render_keys_generated.append(render_key)
                continue
        if required:
            missing.append(section_name)
    return {
        "expected": expected,
        "user_provided": user_provided,
        "strategy_generated": [],
        "legacy_compat_used": legacy_compat_used,
        "render_keys_generated": render_keys_generated,
        "template_defaults": [],
        "missing": missing,
    }


def collect_template_placeholders(template_payload: dict[str, Any]) -> set[str]:
    placeholders = set(template_payload.get("required_placeholders") or [])
    placeholders.update((template_payload.get("default_values") or {}).keys())
    card_placeholders: set[str] = set()
    collect_placeholders(template_payload.get("card") or {}, card_placeholders)
    placeholders.update(card_placeholders)
    return placeholders


def build_smart_hints(args: argparse.Namespace, *, base_key: str | None, template_name: str, template_payload: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    placeholders = collect_template_placeholders(template_payload)
    business_status = business_field_status(template_payload, data)
    supported_levels = supported_detail_levels(base_key)
    recommended_level, recommendation_reasons = compute_recommended_detail_level(base_key, data, args)
    has_annex_link = bool(args.annex_link or data.get("annex_link"))
    warnings: list[str] = []
    suggestions: list[str] = []
    info: list[str] = []
    violations: list[dict[str, str]] = []

    if recommended_level and args.detail_level != recommended_level and args.template is None:
        suggestions.append(f"当前更像 {recommended_level} 场景；可考虑改用 --detail-level {recommended_level}")

    if has_annex_link and args.detail_level != "rich":
        message = "已提供 annex_link，但当前不是 rich；建议改用 --detail-level rich"
        warnings.append(message)
        violations.append({"code": "ANNEX_REQUIRES_RICH", "message": message})

    if args.detail_level == "rich" and not has_annex_link:
        message = "当前为 rich，但未提供 annex_link；建议补 annex 入口"
        warnings.append(message)
        violations.append({"code": "RICH_REQUIRES_ANNEX", "message": message})

    if args.detail_level == "short" and count_populated_fields(data) >= 9:
        warnings.append("当前为 short，但字段较多；建议评估是否切到 standard 或 rich")

    role_values = {
        "target": [args.target],
        "next_owner": args.next_owner,
        "collaborator": args.collaborator,
        "closer": args.closer,
        "decision_maker": args.decision_maker,
    }
    for role_name, values in role_values.items():
        placeholder = ROLE_PLACEHOLDER_HINTS[role_name]
        if values and placeholder not in placeholders:
            message = f"已传 {role_name} 参数，但模板未声明 {placeholder}；可能导致 mention 未进入卡面"
            warnings.append(message)
            violations.append({"code": "ROLE_PLACEHOLDER_MISSING", "message": message})

    if business_status["missing"]:
        message = f"业务区块缺失显式字段：{', '.join(business_status['missing'])}"
        warnings.append(message)
        violations.append({"code": "BUSINESS_PLACEHOLDERS_MISSING", "message": message})
    if business_status.get("legacy_compat_used"):
        legacy_parts = [f"{section}: {', '.join(keys)}" for section, keys in business_status["legacy_compat_used"].items()]
        warnings.append(f"业务区块仍使用旧字段兼容输入：{' ; '.join(legacy_parts)}")
    if business_status["template_defaults"]:
        message = f"业务区块仍依赖模板默认值：{', '.join(business_status['template_defaults'])}"
        warnings.append(message)
        violations.append({"code": "BUSINESS_PLACEHOLDERS_DEFAULTED", "message": message})

    if args.label == "仲裁" and args.detail_level == "short":
        warnings.append("仲裁通常不建议 short，建议保持 standard")
    if args.label == "派单" and args.detail_level == "standard" and args.annex_link:
        suggestions.append("派单已带 annex，更适合 rich 摘要卡 + annex 结构")
    if args.label == "交付" and args.detail_level == "standard" and args.annex_link:
        suggestions.append("交付已带 annex，更适合 rich 交付卡")

    if supported_levels:
        info.append(f"template_key={base_key or '-'} 支持层级：{', '.join(supported_levels)}")
    info.append(f"当前模板：{template_name}")
    info.append(f"字段数={count_populated_fields(data)}，文本载荷≈{text_burden(data)}")

    return {
        "enabled": True,
        "base_template_key": base_key,
        "current_detail_level": args.detail_level,
        "supported_detail_levels": supported_levels,
        "recommended_detail_level": recommended_level,
        "recommendation_reasons": recommendation_reasons,
        "warnings": warnings,
        "suggestions": suggestions,
        "info": info,
        "business_fields": business_status,
        "violations": violations,
        "strict_blocking": bool(violations),
    }


def build_interactive_command(args: argparse.Namespace) -> tuple[list[str], str | None, str | None, dict[str, Any], str, dict[str, Any]]:
    template, resolved_template_key = resolve_interactive_template(args)
    data = merge_interactive_data(args)
    data_path = maybe_build_interactive_data_file(data, args.data)
    cmd = [
        sys.executable,
        str(INTERACTIVE_SENDER),
        "--template",
        template,
        "--target",
        args.target,
        "--chat",
        args.chat,
        "--identity",
        args.identity,
    ]
    if data_path:
        cmd.extend(["--data", data_path])
    for next_owner in args.next_owner:
        cmd.extend(["--next-owner", next_owner])
    for collaborator in args.collaborator:
        cmd.extend(["--collaborator", collaborator])
    for closer in args.closer:
        cmd.extend(["--closer", closer])
    for decision_maker in args.decision_maker:
        cmd.extend(["--decision-maker", decision_maker])
    if args.allow_alias_name:
        cmd.append("--allow-alias-name")
    if args.strict_mentions:
        cmd.append("--strict-mentions")
    if args.dry_run:
        cmd.append("--dry-run")
    template_payload = load_template_payload(template)
    return cmd, resolved_template_key, data_path, data, template, template_payload


def build_receipt(delegate_stdout: Any, *, label: str, target: str, preset: str, dry_run: bool, message_format: str) -> dict[str, Any] | None:
    if not isinstance(delegate_stdout, dict):
        return None
    mode = delegate_stdout.get("mode")
    if mode == "dry_run":
        chat = delegate_stdout.get("chat") or {}
        sender = delegate_stdout.get("sender_identity") or {}
        runtime_env = delegate_stdout.get("runtime_env") or {}
        target_info = delegate_stdout.get("target") or {}
        required_targets = delegate_stdout.get("required_targets") or []
        if not target_info and required_targets:
            target_info = required_targets[0]
        return {
            "status": "DRY_RUN_OK",
            "format": message_format,
            "label": label,
            "target": target,
            "preset": preset,
            "dry_run": dry_run,
            "message_id": None,
            "chat_id": chat.get("chat_id"),
            "sender_type": sender.get("sender_type"),
            "sender_id": sender.get("sender_id"),
            "target_open_id": target_info.get("canonical_open_id") or target_info.get("open_id"),
            "target_display_name": target_info.get("display_name"),
            "canonical_open_id": target_info.get("canonical_open_id") or target_info.get("open_id"),
            "allowed_open_ids_for_sender": target_info.get("allowed_open_ids_for_sender") or [],
            "next_owner_display_names": [item.get("display_name") for item in (delegate_stdout.get("next_owners") or [])],
            "next_owner_open_ids": [item.get("canonical_open_id") for item in (delegate_stdout.get("next_owners") or [])],
            "required_targets": required_targets,
            "actual_mention_open_id": None,
            "compat_mode": False,
            "mention_verified": False,
            "runtime_env_path": runtime_env.get("active_env_path"),
        }
    if mode in {"send_and_verify", "verify_existing"}:
        checks = delegate_stdout.get("checks") or {}
        expected = delegate_stdout.get("expected") or {}
        runtime_env = delegate_stdout.get("runtime_env") or {}
        return {
            "status": "VERIFIED" if delegate_stdout.get("ok") else "FAILED",
            "format": message_format,
            "label": label,
            "target": target,
            "preset": preset,
            "dry_run": dry_run,
            "message_id": delegate_stdout.get("message_id"),
            "chat_id": delegate_stdout.get("chat_id"),
            "sender_type": delegate_stdout.get("sender_type"),
            "sender_id": delegate_stdout.get("sender_id"),
            "target_open_id": expected.get("target_open_id"),
            "target_display_name": expected.get("target_display_name"),
            "canonical_open_id": expected.get("canonical_open_id") or expected.get("target_open_id"),
            "allowed_open_ids_for_sender": expected.get("allowed_open_ids_for_sender") or [],
            "next_owner_display_names": expected.get("next_owner_display_names") or [],
            "next_owner_open_ids": expected.get("next_owner_open_ids") or [],
            "required_targets": expected.get("required_targets") or [],
            "actual_mention_open_id": delegate_stdout.get("actual_mention_open_id"),
            "compat_mode": bool(delegate_stdout.get("compat_mode")),
            "mention_verified": bool(delegate_stdout.get("ok")),
            "verification_checks": checks,
            "runtime_env_path": runtime_env.get("active_env_path"),
        }
    if mode == "send_and_verify_interactive_formal":
        checks = delegate_stdout.get("checks") or {}
        runtime_env = delegate_stdout.get("runtime_env") or {}
        target_checks = delegate_stdout.get("target_checks") or []
        primary = target_checks[0] if target_checks else {}
        return {
            "status": "VERIFIED" if delegate_stdout.get("transport_ok") else "FAILED",
            "format": "interactive",
            "label": label,
            "target": target,
            "preset": preset,
            "dry_run": dry_run,
            "message_id": delegate_stdout.get("message_id"),
            "chat_id": delegate_stdout.get("chat_id"),
            "sender_type": delegate_stdout.get("sender_type"),
            "sender_id": delegate_stdout.get("sender_id"),
            "target_open_id": primary.get("canonical_open_id"),
            "target_display_name": primary.get("display_name"),
            "canonical_open_id": primary.get("canonical_open_id"),
            "allowed_open_ids_for_sender": primary.get("allowed_open_ids_for_sender") or [],
            "required_targets": target_checks,
            "actual_mention_open_id": delegate_stdout.get("mention_ids", [None])[0] if delegate_stdout.get("mention_ids") else None,
            "compat_mode": not bool(delegate_stdout.get("mention_names_present")),
            "mention_verified": bool(delegate_stdout.get("mention_verified")),
            "verification_checks": checks,
            "runtime_env_path": runtime_env.get("active_env_path"),
        }
    return None


def resolve_effective_format(args: argparse.Namespace) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if args.format == "interactive":
        reasons.append("explicit --format interactive")
        return "interactive", reasons
    if args.format == "text":
        reasons.append("explicit --format text")
        return "text", reasons

    interactive_inputs_present = bool(
        args.template
        or args.template_key
        or args.data
        or args.annex_link
        or args.annex_title
        or args.annex_summary
        or args.collaborator
        or args.closer
        or args.decision_maker
        or args.next_owner
        or base_template_key_for_args(args)
    )
    if interactive_inputs_present:
        reasons.append("auto mode: detected interactive-compatible label/inputs, prefer interactive")
        return "interactive", reasons
    if args.text.strip():
        reasons.append("auto mode: no interactive path detected, fall back to text because body text is present")
        return "text", reasons
    reasons.append("auto mode: interactive preferred by policy, but no template mapping/data or text body supplied")
    raise ValueError("auto mode could not resolve a send path; provide interactive data/template or explicit --format text with body text")


def info_density_strategy(args: argparse.Namespace, effective_format: str, merged_data: dict[str, Any] | None) -> dict[str, Any]:
    data = merged_data or {}
    fields = count_populated_fields(data)
    burden = text_burden(data)
    has_annex = bool(args.annex_link or data.get("annex_link"))
    report_like_label = args.label in {"派单", "进展", "交付", "结论", "受理", "催办"}
    report_like_payload = fields >= 8 or burden >= 220
    requires_longform = report_like_label and (report_like_payload or has_annex)
    strategy = {
        "effective_format": effective_format,
        "fields": fields,
        "text_burden": burden,
        "has_annex": has_annex,
        "requires_longform": requires_longform,
        "recommended_pattern": "summary_card_only",
        "recommendations": [],
    }
    if effective_format == "interactive":
        if has_annex:
            strategy["recommended_pattern"] = "summary_card_plus_annex"
            strategy["recommendations"].append("当前已具备 annex，可采用『卡片摘要 + 长文附录』双层结构")
        elif requires_longform:
            strategy["recommended_pattern"] = "summary_card_plus_followup"
            strategy["recommendations"].append("当前信息量偏高，建议先发模板卡片摘要，再补长文附件/链接/〔补充〕说明")
        else:
            strategy["recommendations"].append("当前信息量适合单卡承载")
    else:
        strategy["recommended_pattern"] = "text_fallback_only"
        strategy["recommendations"].append("text 仅作显式降级兜底；正式治理默认应回到 interactive 模板")
    return strategy


def main() -> int:
    args = parse_args()
    effective_format, format_reasons = resolve_effective_format(args)
    resolved_template_key = args.template_key
    temp_data_path = None
    smart_hints = None
    self_check = None
    strict_blocking = False
    merged_data: dict[str, Any] | None = None
    if effective_format == "interactive":
        cmd, resolved_template_key, temp_data_path, merged_data, template_name, template_payload = build_interactive_command(args)
        if not args.no_smart_hints:
            smart_hints = build_smart_hints(
                args,
                base_key=resolved_template_key or base_template_key_for_args(args),
                template_name=template_name,
                template_payload=template_payload,
                data=merged_data,
            )
            strict_blocking = bool(smart_hints.get("strict_blocking"))
            info_density = info_density_strategy(args, effective_format, merged_data)
            smart_hints.setdefault("info", []).append(
                f"信息量策略：{info_density['recommended_pattern']}（fields={info_density['fields']} burden≈{info_density['text_burden']} annex={info_density['has_annex']}）"
            )
            for rec in info_density["recommendations"]:
                smart_hints.setdefault("suggestions", []).append(rec)
        self_check = {
            "mode": "self_check",
            "template": template_name,
            "template_key": resolved_template_key,
            "detail_level": args.detail_level,
            "required_placeholders": template_payload.get("required_placeholders") or [],
            "available_placeholders": sorted(collect_template_placeholders(template_payload)),
            "provided_data_keys": sorted(merged_data.keys()),
            "business_field_status": business_field_status(template_payload, merged_data),
            "role_arguments": {
                "target": args.target,
                "next_owner": args.next_owner,
                "collaborator": args.collaborator,
                "closer": args.closer,
                "decision_maker": args.decision_maker,
            },
        }
    else:
        cmd = build_text_command(args)
        self_check = {
            "mode": "self_check",
            "format": "text",
            "label": args.label,
            "target": args.target,
            "text_preview": render_text(args.text, args.preset),
            "next_owner": args.next_owner,
        }

    payload = {
        "wrapper": str(Path(__file__).name),
        "requested_format": args.format,
        "format": effective_format,
        "format_resolution": format_reasons,
        "detail_level": args.detail_level if effective_format == "interactive" else None,
        "template_key": resolved_template_key,
        "delegated_command": cmd,
        "policy": {
            "interactive_default": True,
            "text_is_explicit_fallback_only": True,
        },
    }
    if smart_hints is not None:
        payload["smart_hints"] = smart_hints
    if args.self_check:
        payload["self_check"] = self_check
        payload["exit_code"] = 2 if args.strict_hints and strict_blocking else 0
        payload["strict_hints_triggered"] = bool(args.strict_hints and strict_blocking)
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr if payload["exit_code"] else sys.stdout)
        if temp_data_path and os.path.exists(temp_data_path):
            os.unlink(temp_data_path)
        return payload["exit_code"]

    if args.strict_hints and strict_blocking:
        payload["exit_code"] = 2
        payload["strict_hints_triggered"] = True
        payload["delegate_stderr"] = "strict hints blocked send"
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        if temp_data_path and os.path.exists(temp_data_path):
            os.unlink(temp_data_path)
        return 2

    try:
        proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
    finally:
        if temp_data_path and os.path.exists(temp_data_path):
            os.unlink(temp_data_path)

    payload["exit_code"] = proc.returncode
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if stdout:
        try:
            payload["delegate_stdout"] = json.loads(stdout)
        except json.JSONDecodeError:
            payload["delegate_stdout"] = stdout
    if stderr:
        payload["delegate_stderr"] = stderr
    receipt = build_receipt(
        payload.get("delegate_stdout"),
        label=args.label,
        target=args.target,
        preset=args.preset,
        dry_run=args.dry_run,
        message_format=effective_format,
    )
    if receipt:
        payload["receipt"] = receipt
    stream = sys.stdout if proc.returncode == 0 else sys.stderr
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
