#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates"

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render a Feishu interactive card from a template + field data")
    p.add_argument("--template", required=True, help="Template file name or absolute path")
    p.add_argument("--data", help="JSON string or path to JSON file containing field data")
    p.add_argument("--pretty", action="store_true", help="Pretty-print output JSON")
    p.add_argument("--envelope", action="store_true", help="Wrap result as Feishu send-message payload")
    p.add_argument("--receive-id", help="Required when --envelope is used")
    return p.parse_args()


def load_json_input(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(raw)
    try:
        candidate = Path(raw).expanduser()
        if candidate.exists():
            return json.loads(candidate.read_text())
    except OSError:
        pass
    return json.loads(raw)


def resolve_template_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if p.exists():
        return p
    p = TEMPLATE_DIR / raw
    if p.exists():
        return p
    raise FileNotFoundError(f"Template not found: {raw}")


def at(open_id: str) -> str:
    return f'<at id="{open_id}"></at>'


def normalize_value(key: str, value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "mention_token" in value:
            return str(value["mention_token"])
        if "open_id" in value:
            return at(str(value["open_id"]))
        if "display_name" in value:
            return str(value["display_name"])
    if isinstance(value, list):
        if not value:
            return "-"
        return "、".join(normalize_value(key, item) for item in value)
    return str(value)


def deep_replace(node: Any, mapping: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {k: deep_replace(v, mapping) for k, v in node.items()}
    if isinstance(node, list):
        return [deep_replace(v, mapping) for v in node]
    if isinstance(node, str):
        return PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(1), m.group(0)), node)
    return node


def collect_missing(node: Any, available: set[str], missing: set[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            collect_missing(v, available, missing)
    elif isinstance(node, list):
        for v in node:
            collect_missing(v, available, missing)
    elif isinstance(node, str):
        for match in PLACEHOLDER_RE.findall(node):
            if match not in available:
                missing.add(match)


def collect_placeholders(node: Any, placeholders: set[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            collect_placeholders(v, placeholders)
    elif isinstance(node, list):
        for v in node:
            collect_placeholders(v, placeholders)
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


def format_bullet_lines(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def business_sections(template_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sections = template_payload.get("business_sections") or {}
    return sections if isinstance(sections, dict) else {}


def normalize_business_sections(template_payload: dict[str, Any], data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = dict(data)
    status = {
        "expected": [],
        "user_provided": [],
        "legacy_compat_used": {},
        "render_keys_generated": [],
        "missing": [],
    }
    for section_name, cfg in business_sections(template_payload).items():
        if not isinstance(cfg, dict):
            continue
        render_key = cfg.get("render_key") or f"{section_name}_md"
        legacy_prefix = cfg.get("legacy_prefix")
        max_items = cfg.get("max_items")
        required = bool(cfg.get("required"))
        status["expected"].append(section_name)

        items = normalize_section_items(data.get(section_name))
        if items:
            status["user_provided"].append(section_name)
        elif legacy_prefix:
            items = collect_legacy_numbered_values(data, legacy_prefix)
            if items:
                status["legacy_compat_used"][section_name] = [f"{legacy_prefix}{idx}" for idx in range(1, len(items) + 1)]
        if max_items:
            items = items[: int(max_items)]
        if items:
            normalized[section_name] = items
            normalized[render_key] = format_bullet_lines(items)
            status["render_keys_generated"].append(render_key)
        elif required:
            status["missing"].append(section_name)
    return normalized, status


def build_mapping(template_payload: dict[str, Any], data: dict[str, Any]) -> dict[str, str]:
    normalized_data, _ = normalize_business_sections(template_payload, data)
    merged: dict[str, Any] = {}
    merged.update(template_payload.get("default_values") or {})
    merged.update(normalized_data)
    return {k: normalize_value(k, v) for k, v in merged.items()}


def main() -> int:
    args = parse_args()
    template_path = resolve_template_path(args.template)
    template_payload = json.loads(template_path.read_text())
    data = load_json_input(args.data)
    normalized_data, business_status = normalize_business_sections(template_payload, data)
    if business_status["missing"]:
        raise SystemExit(f"Missing business placeholders: {', '.join(business_status['missing'])}")
    mapping = build_mapping(template_payload, normalized_data)

    required = template_payload.get("required_placeholders") or []
    missing_required = [key for key in required if key not in mapping or mapping[key] in {"", "-"}]
    if missing_required:
        raise SystemExit(f"Missing required placeholders: {', '.join(missing_required)}")

    card = template_payload.get("card")
    if not isinstance(card, dict):
        raise SystemExit("Template missing 'card' object")

    unresolved: set[str] = set()
    collect_missing(card, set(mapping.keys()), unresolved)
    if unresolved:
        raise SystemExit(f"Template contains unresolved placeholders without values/defaults: {', '.join(sorted(unresolved))}")

    rendered = deep_replace(card, mapping)
    output: Any = rendered
    if args.envelope:
        if not args.receive_id:
            raise SystemExit("--receive-id is required with --envelope")
        output = {
            "receive_id": args.receive_id,
            "msg_type": "interactive",
            "content": json.dumps(rendered, ensure_ascii=False),
        }

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
