#!/usr/bin/env python3
"""Batch remediation helper for Feishu four-table alignment.

Default mode is dry-run against exported JSON snapshots under tmp/bitable_exports_2026-04-18.
Use --apply together with Feishu credentials to write updates/new records back to Feishu.

Examples:
  python scripts/remediate_tables.py
  python scripts/remediate_tables.py --tables shotplan,scene
  python scripts/remediate_tables.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MIDDLEWARE_DIR = REPO_ROOT / "middleware"
if str(MIDDLEWARE_DIR) not in sys.path:
    sys.path.insert(0, str(MIDDLEWARE_DIR))

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

try:
    from adapters.feishu import FeishuClient
except Exception:  # pragma: no cover
    FeishuClient = None


def _load_env_fallback(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


if load_dotenv:
    load_dotenv(MIDDLEWARE_DIR / ".env")
else:
    _load_env_fallback(MIDDLEWARE_DIR / ".env")

TABLE_IDS = {
    "strategy": "tblu2EzR78tWjYf6",
    "shotplan": "tbl0xCaqru1TjwzK",
    "scene": "tbliWlwiyA4sppgY",
    "persona": "tblxSbOoZ2kMCkc6",
}

EXPORT_FILENAMES = {
    "strategy": "strategy.json",
    "shotplan": "shotplan.json",
    "scene": "scene.json",
    "persona": "persona.json",
}

DEFAULT_EXPORT_DIR = REPO_ROOT / "tmp" / "bitable_exports_2026-04-18"
CONTENT_TYPES = [
    "种草推荐", "好物分享", "深度测评", "对比测评", "穿搭搭配",
    "场景展示", "日常vlog", "开箱", "买家秀/晒单", "节日/活动限定",
    "新品发布", "选购攻略/使用教程",
]
PERSONA_TAGS = ["甜酷", "清冷", "青春", "精致", "松弛", "中性简洁"]
SCENE_TAGS = ["商场", "通勤", "校园", "居家", "街头", "咖啡馆", "户外", "礼物", "棚拍"]


@dataclass
class Operation:
    table: str
    action: str
    code: str
    record_id: str | None
    fields: dict[str, Any]


def _rich_text_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "".join(seg.get("text", "") if isinstance(seg, dict) else str(seg) for seg in value)
    return str(value)


def _single_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("text", ""))
    return str(value)


def _multi_to_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                result.append(str(item.get("text", "")))
            else:
                result.append(str(item))
        return [v for v in result if v]
    return []


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _normalize_content_types(values: list[str]) -> list[str]:
    mapping = {
        "种草图文": "种草推荐",
        "产品展示": "好物分享",
    }
    normalized = [mapping.get(v, v) for v in values]
    normalized = [v for v in normalized if v in CONTENT_TYPES]
    return _dedupe(normalized)


def _parse_story_nodes(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return json.dumps([], ensure_ascii=False)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        pass
    parts = [p.strip(" -•\t") for p in re.split(r"\s*(?:→|->|/|\n|\|)\s*", raw) if p.strip()]
    return json.dumps(parts or [raw], ensure_ascii=False)


def _next_code(records: list[dict], field_name: str, prefix: str, width: int = 3) -> str:
    max_id = 0
    for r in records:
        code = _rich_text_to_str(r.get("fields", {}).get(field_name))
        m = re.match(rf"^{re.escape(prefix)}(\d+)$", code)
        if m:
            max_id = max(max_id, int(m.group(1)))
    return f"{prefix}{max_id + 1:0{width}d}"


def _load_records(table: str, export_dir: Path, live: bool, client: Any | None) -> list[dict]:
    if live:
        return client.list_records(TABLE_IDS[table])
    path = export_dir / EXPORT_FILENAMES[table]
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _strategy_defaults(record: dict) -> dict[str, Any]:
    fields = record["fields"]
    content_types = _normalize_content_types(_multi_to_list(fields.get("适用内容类型")))
    content_type = content_types[0] if content_types else "种草推荐"
    strategy_name = _rich_text_to_str(fields.get("策略名称"))
    tone = _single_to_str(fields.get("情绪基调")) or "松弛感"
    angle = _single_to_str(fields.get("切入角度")) or "精致生活"

    angle_tags_map = {
        "种草推荐": ["氛围感种草", "细节质感"],
        "好物分享": ["日常实用", "细节质感"],
        "深度测评": ["日常实用", "细节质感"],
        "对比测评": ["日常实用", "礼物推荐"],
        "穿搭搭配": ["搭配点睛", "氛围感种草"],
        "场景展示": ["氛围感种草", "日常实用"],
        "日常vlog": ["氛围感种草", "日常实用"],
        "开箱": ["细节质感", "礼物推荐"],
        "买家秀/晒单": ["氛围感种草", "日常实用"],
        "节日/活动限定": ["礼物推荐", "氛围感种草"],
        "新品发布": ["细节质感", "氛围感种草"],
        "选购攻略/使用教程": ["日常实用", "细节质感"],
    }
    structure_map = {
        "种草推荐": "情绪切入",
        "好物分享": "体验切入",
        "深度测评": "体验切入",
        "对比测评": "对比切入",
        "穿搭搭配": "场景切入",
        "场景展示": "场景切入",
        "日常vlog": "场景切入",
        "开箱": "体验切入",
        "买家秀/晒单": "体验切入",
        "节日/活动限定": "情绪切入",
        "新品发布": "痛点切入",
        "选购攻略/使用教程": "痛点切入",
    }
    persona_map = {
        "种草推荐": ["甜酷", "精致"],
        "好物分享": ["松弛", "精致"],
        "深度测评": ["中性简洁", "清冷"],
        "对比测评": ["中性简洁", "清冷"],
        "穿搭搭配": ["甜酷", "青春"],
        "场景展示": ["松弛", "精致"],
        "日常vlog": ["青春", "松弛"],
        "开箱": ["青春", "精致"],
        "买家秀/晒单": ["青春", "松弛"],
        "节日/活动限定": ["精致", "甜酷"],
        "新品发布": ["精致", "清冷"],
        "选购攻略/使用教程": ["中性简洁", "精致"],
    }

    return {
        "标题句式池": f"{strategy_name}｜{content_type}｜{tone}\n被问爆的{content_type}灵感来了\n{angle}风内容这样写更容易出片",
        "叙事角度标签": angle_tags_map.get(content_type, ["日常实用", "细节质感"]),
        "结构模式": structure_map.get(content_type, "体验切入"),
        "差异化提示模板": f"围绕{angle}与{tone}展开，不重复常见套路，优先突出手机壳/手机链在具体生活场景中的可见变化。",
        "人设适配标签": persona_map.get(content_type, ["精致", "松弛"]),
        "正文禁忌": "避免空泛夸张、避免堆砌参数、避免与平台热点标签强绑定。",
    }


def _existing_text_set(records: list[dict], field_name: str) -> set[str]:
    values: set[str] = set()
    for record in records:
        value = _rich_text_to_str(record.get("fields", {}).get(field_name)).strip()
        if value:
            values.add(value)
    return values


def remediate_strategy(records: list[dict]) -> list[Operation]:
    ops: list[Operation] = []
    for record in records:
        fields = record["fields"]
        patch: dict[str, Any] = {}
        defaults = _strategy_defaults(record)
        for key, value in defaults.items():
            current = fields.get(key)
            if current in (None, "", []):
                patch[key] = value
        story = _rich_text_to_str(fields.get("文案叙事节点"))
        normalized_story = _parse_story_nodes(story)
        if story and normalized_story != story:
            patch["文案叙事节点"] = normalized_story
        if patch:
            ops.append(Operation(
                table="strategy",
                action="update",
                code=_rich_text_to_str(fields.get("策略编号")),
                record_id=record.get("record_id"),
                fields=patch,
            ))

    next_code = _next_code(records, "策略编号", "ST")
    existing_names = _existing_text_set(records, "策略名称")
    template_records = [
        {
            "策略名称": "手机链穿搭点睛型",
            "切入角度": "社交货币",
            "情绪基调": "兴奋感",
            "表达方式": "生活记录感种草",
            "适用内容类型": ["穿搭搭配", "种草推荐"],
            "适用平台": ["小红书", "得物"],
            "适用品类": ["手机链", "手机壳"],
        },
        {
            "策略名称": "手机壳细节质感型",
            "切入角度": "精致生活",
            "情绪基调": "高冷极简",
            "表达方式": "朋友推荐",
            "适用内容类型": ["种草推荐", "好物分享", "新品发布"],
            "适用平台": ["小红书", "得物"],
            "适用品类": ["手机壳"],
        },
        {
            "策略名称": "手机壳+手机链组合搭配型",
            "切入角度": "精致生活",
            "情绪基调": "松弛感",
            "表达方式": "场景故事",
            "适用内容类型": ["穿搭搭配", "场景展示", "种草推荐"],
            "适用平台": ["小红书", "得物"],
            "适用品类": ["手机壳", "手机链"],
        },
        {
            "策略名称": "礼物送女生场景型",
            "切入角度": "情感共鸣",
            "情绪基调": "温暖亲密",
            "表达方式": "朋友推荐",
            "适用内容类型": ["节日/活动限定", "开箱", "好物分享"],
            "适用平台": ["小红书", "得物"],
            "适用品类": ["手机壳", "手机链"],
        },
    ]
    next_num = int(re.search(r"(\d+)$", next_code).group(1))
    for item in template_records:
        if item["策略名称"] in existing_names:
            continue
        code = f"ST{next_num:03d}"
        next_num += 1
        fake = {"fields": item}
        fields = {
            "策略编号": code,
            "是否启用": "启用",
            "优先级": 80,
            "系统提示词前缀": "围绕主营品类手机壳/手机链生成具体、可执行、平台友好的高信息密度文案。",
            "文案叙事节点": _parse_story_nodes("场景引入 → 产品亮点 → 使用变化 → 结尾种草"),
            "标题写作指南": "标题优先写具体场景、明确对象和感知收益。",
            **item,
            **_strategy_defaults(fake),
        }
        ops.append(Operation("strategy", "create", code, None, fields))
    return ops


def remediate_shotplan(records: list[dict]) -> list[Operation]:
    ops: list[Operation] = []
    for record in records:
        fields = record["fields"]
        patch: dict[str, Any] = {}
        forms = _multi_to_list(fields.get("适用内容形态"))
        if not forms or any(v in {"图片生成", "组图", "图片"} for v in forms):
            normalized_forms = ["图片"]
            if normalized_forms != forms:
                patch["适用内容形态"] = normalized_forms
        content_types = _normalize_content_types(_multi_to_list(fields.get("适用内容类型")))
        if content_types and content_types != _multi_to_list(fields.get("适用内容类型")):
            patch["适用内容类型"] = content_types
        if fields.get("禁止重复镜头") in (None, "", []):
            patch["禁止重复镜头"] = "避免连续相同景别、相同手持角度和重复纯背景主图。"
        if fields.get("动作变化要求") in (None, "", []):
            patch["动作变化要求"] = "同一方案内至少覆盖 2 种以上构图/持握/摆放变化，避免整组画面节奏单一。"
        if patch:
            ops.append(Operation(
                table="shotplan",
                action="update",
                code=_rich_text_to_str(fields.get("方案编号")),
                record_id=record.get("record_id"),
                fields=patch,
            ))

    next_code = _next_code(records, "方案编号", "SP")
    existing_names = _existing_text_set(records, "方案名称")
    next_num = int(re.search(r"(\d+)$", next_code).group(1))
    new_records = [
        {
            "方案名称": "手机壳装机效果4图",
            "适用内容类型": ["种草推荐", "好物分享"],
            "适用品类": ["手机壳"],
            "节点数量": 4,
            "角色序列": [
                "装机主图，展示正背面整体视觉与贴合度，{scene_description}",
                "边框按键与镜头位特写，突出做工与开孔细节，{scene_description}",
                "手持使用状态，展示握持感与真实生活使用姿态，{scene_description}",
                "桌面或包内收纳场景，强化日常搭配和便携价值，{scene_description}",
            ],
        },
        {
            "方案名称": "手机壳+手机链组合搭配5图",
            "适用内容类型": ["穿搭搭配", "场景展示"],
            "适用品类": ["手机壳", "手机链"],
            "节点数量": 5,
            "角色序列": [
                "整体搭配全景，手机壳与手机链同步出镜，{scene_description}",
                "人物上身中景，展示挂链佩戴或手提状态，{scene_description}",
                "局部五金/挂点/材质特写，{scene_description}",
                "切换第二种动作或穿搭状态，强化组合差异，{scene_description}",
                "情绪氛围收尾，突出整套搭配完成度，{scene_description}",
            ],
        },
        {
            "方案名称": "手机链细节质感测评5图",
            "适用内容类型": ["深度测评", "对比测评"],
            "适用品类": ["手机链"],
            "节点数量": 5,
            "角色序列": [
                "手机链整体展示，结构与长度清晰可见，{scene_description}",
                "挂点、扣件、五金细节近拍，{scene_description}",
                "上身或手持使用状态，展示长度与垂坠感，{scene_description}",
                "受力/耐用场景或细节对比镜头，{scene_description}",
                "收尾总结图，强调日常通勤/出街适配性，{scene_description}",
            ],
        },
        {
            "方案名称": "礼物开箱展示5图",
            "适用内容类型": ["开箱", "节日/活动限定"],
            "适用品类": ["手机壳", "手机链"],
            "节点数量": 5,
            "角色序列": [
                "礼盒完整呈现，营造送礼仪式感，{scene_description}",
                "打开包装第一视角，展示惊喜时刻，{scene_description}",
                "产品与包装细节同框特写，{scene_description}",
                "试戴/试装使用镜头，呈现收到礼物后的真实状态，{scene_description}",
                "情绪收尾图，强化礼物属性与出片氛围，{scene_description}",
            ],
        },
    ]
    for item in new_records:
        if item["方案名称"] in existing_names:
            continue
        code = f"SP{next_num:03d}"
        next_num += 1
        fields = {
            "方案编号": code,
            "是否启用": "启用",
            "适用内容形态": ["图片"],
            "构图节奏": "丰富",
            "人物出镜比例": "中等",
            "道具密度": "中",
            "禁止重复镜头": "避免连续相同景别、相同手持角度和重复纯背景主图。",
            "动作变化要求": "同一方案内至少覆盖 2 种以上构图/持握/摆放变化，避免整组画面节奏单一。",
            **item,
        }
        fields["角色序列"] = json.dumps([
            {"index": idx + 1, "zh": text, "en": text}
            for idx, text in enumerate(item["角色序列"])
        ], ensure_ascii=False)
        ops.append(Operation("shotplan", "create", code, None, fields))
    return ops


def _scene_theme(fields: dict) -> str:
    name = _rich_text_to_str(fields.get("场景名称"))
    scene_type = _single_to_str(fields.get("场景类型"))
    text = f"{name} {scene_type}"
    mapping = [
        ("咖啡", "咖啡馆"), ("书店", "咖啡馆"), ("校园", "校园"), ("学习", "校园"),
        ("通勤", "通勤"), ("办公室", "通勤"), ("电梯", "通勤"), ("街", "街头"),
        ("户外", "户外"), ("公园", "户外"), ("居家", "居家"), ("家居", "居家"),
        ("礼", "礼物"), ("棚拍", "棚拍"), ("商场", "商场"),
    ]
    for needle, theme in mapping:
        if needle in text:
            return theme
    return "居家"


def _scene_persona_tags(theme: str, person_type: str) -> list[str]:
    theme_map = {
        "咖啡馆": ["清冷", "精致"],
        "校园": ["青春", "甜酷"],
        "通勤": ["精致", "中性简洁"],
        "街头": ["甜酷", "松弛"],
        "户外": ["松弛", "青春"],
        "居家": ["松弛", "精致"],
        "礼物": ["精致", "甜酷"],
        "棚拍": ["清冷", "中性简洁"],
        "商场": ["精致", "甜酷"],
    }
    tags = theme_map.get(theme, ["精致", "松弛"])
    if person_type == "无人物·纯产品":
        tags = ["中性简洁", tags[0]]
    return _dedupe(tags)


def _normalize_scene_person_type(value: str) -> str:
    mapping = {
        "真人出镜": "有人物·主体",
        "真人出镜（双人）": "有人物·主体",
        "局部入镜（手部）": "有人物·局部",
        "有人物·局部手部": "有人物·局部",
        "无人物": "无人物·纯产品",
        "可无人物": "可有人物",
        "可无人物/手部入镜": "可有人物",
    }
    return mapping.get(value, value)


def _scene_tech_defaults(theme: str, person_type: str) -> dict[str, str]:
    return {
        "姿态倾向": "自然放松" if person_type != "无人物·纯产品" else "专注操作",
        "光线方向": "侧光" if theme not in {"棚拍", "礼物"} else "漫射·无明显方向",
        "色温": "暖调(3200K)" if theme in {"礼物", "居家", "咖啡馆"} else "中性日光(5500K)",
        "景深感": "浅景深·背景虚化" if person_type != "无人物·纯产品" else "中等景深",
        "镜头感": "85mm人像感" if person_type in {"有人物·主体", "有人物·局部"} else "50mm标准",
    }


def remediate_scene(records: list[dict]) -> list[Operation]:
    ops: list[Operation] = []
    for record in records:
        fields = record["fields"]
        patch: dict[str, Any] = {}

        person_type = _normalize_scene_person_type(_single_to_str(fields.get("人物类型")))
        if person_type and person_type != _single_to_str(fields.get("人物类型")):
            patch["人物类型"] = person_type

        categories = _multi_to_list(fields.get("适用品类"))
        normalized_categories = _dedupe(["充电宝" if v == "充电器" else v for v in categories])
        if normalized_categories != categories:
            patch["适用品类"] = normalized_categories

        theme = _single_to_str(fields.get("场景主题")) or _scene_theme(fields)
        if fields.get("场景主题") in (None, "", []):
            patch["场景主题"] = theme

        if fields.get("道具建议") in (None, "", []):
            patch["道具建议"] = {
                "咖啡馆": "咖啡杯、杂志、托盘、桌面小物",
                "校园": "书本、耳机、帆布包、文具",
                "通勤": "电脑包、工牌、咖啡杯、钥匙",
                "街头": "墨镜、包袋、耳机、街头海报元素",
                "户外": "花束、野餐布、水杯、太阳镜",
                "居家": "香薰、床品、镜子、桌面摆件",
                "礼物": "礼盒、丝带、花束、贺卡",
                "棚拍": "亚克力台座、反光板、纯色背景纸",
                "商场": "购物袋、扶梯、镜面、品牌陈列",
            }.get(theme, "桌面生活道具、布料、收纳摆件")

        if fields.get("光线风格标签") in (None, "", []):
            patch["光线风格标签"] = _dedupe([
                "柔光" if "柔" in _single_to_str(fields.get("光源类型")) or "自然" in _single_to_str(fields.get("光源类型")) else "冷白光",
                "逆光" if "逆光" in _single_to_str(fields.get("光线方向")) else "暖调" if "暖" in _single_to_str(fields.get("色温")) else "冷白光",
            ])

        if fields.get("适合人设标签") in (None, "", []):
            patch["适合人设标签"] = _scene_persona_tags(theme, person_type)

        if fields.get("氛围等级") in (None, "", []):
            patch["氛围等级"] = "高" if theme in {"礼物", "街头", "咖啡馆"} else "中"

        tech_defaults = _scene_tech_defaults(theme, person_type or "可有人物")
        for field_name, default_value in tech_defaults.items():
            if fields.get(field_name) in (None, "", []):
                patch[field_name] = default_value

        if fields.get("差异化备注") in (None, "", []):
            patch["差异化备注"] = f"优先输出与{theme}相关的道具和空间层次差异，避免同一类场景重复背景。"

        if patch:
            ops.append(Operation(
                table="scene",
                action="update",
                code=_rich_text_to_str(fields.get("场景编号")),
                record_id=record.get("record_id"),
                fields=patch,
            ))

    next_code = _next_code(records, "场景编号", "SC")
    existing_names = _existing_text_set(records, "场景名称")
    next_num = int(re.search(r"(\d+)$", next_code).group(1))
    new_records = [
        {"场景名称": "手机壳+手机链组合桌面平铺", "场景主题": "居家", "人物类型": "无人物·纯产品", "适用品类": ["手机壳", "手机链"]},
        {"场景名称": "女性送礼礼盒场景", "场景主题": "礼物", "人物类型": "有人物·局部", "适用品类": ["手机壳", "手机链"]},
        {"场景名称": "职场通勤电梯办公室镜面", "场景主题": "通勤", "人物类型": "有人物·主体", "适用品类": ["手机壳", "手机链"]},
        {"场景名称": "书店咖啡馆轻文艺手机链", "场景主题": "咖啡馆", "人物类型": "有人物·主体", "适用品类": ["手机链"]},
        {"场景名称": "极简冷调棚拍手机壳", "场景主题": "棚拍", "人物类型": "无人物·纯产品", "适用品类": ["手机壳"]},
        {"场景名称": "无人物高质感桌面氛围", "场景主题": "居家", "人物类型": "无人物·纯产品", "适用品类": ["手机壳", "手机链", "充电宝"]},
    ]
    for item in new_records:
        if item["场景名称"] in existing_names:
            continue
        code = f"SC{next_num:03d}"
        next_num += 1
        theme = item["场景主题"]
        person_type = item["人物类型"]
        fields = {
            "场景编号": code,
            "是否启用": "启用",
            "权重": 80,
            "适用平台": ["小红书", "得物"],
            "使用频次": 0,
            "年龄段": "23-28岁职场" if theme == "通勤" else "18-22岁学生" if theme == "校园" else "不指定",
            "性别倾向": "女性" if theme in {"礼物", "咖啡馆", "通勤"} else "不限",
            "外貌风格": "精致通勤" if theme == "通勤" else "自然日系" if theme in {"咖啡馆", "居家"} else "不指定",
            "姿态倾向": "自然放松",
            "场景类型": "棚拍·纯净" if theme == "棚拍" else "室内·家居" if theme == "居家" else "室内·咖啡馆" if theme == "咖啡馆" else "户外·街拍" if theme == "街头" else "室内·工作室",
            "时段光境": "午后",
            "空间感": "中景带环境",
            "光源类型": "自然光" if theme != "棚拍" else "棚拍纯净光",
            "光线方向": "侧光",
            "色温": "中性日光(5500K)",
            "景别": "中景",
            "拍摄角度": "平视",
            "景深感": "中等景深",
            "镜头感": "50mm标准",
            "氛围等级": "高" if theme in {"礼物", "咖啡馆"} else "中",
            "道具建议": {
                "居家": "托盘、香薰、布料、耳机、桌面摆件",
                "礼物": "礼盒、丝带、花束、贺卡",
                "通勤": "电脑包、咖啡杯、工牌、镜面反射",
                "咖啡馆": "咖啡杯、书本、托盘、窗边桌面",
                "棚拍": "亚克力台座、反光板、纯色背景纸",
            }.get(theme, "桌面生活小物、布料、包袋"),
            "光线风格标签": ["柔光", "暖调"] if theme in {"礼物", "咖啡馆", "居家"} else ["冷白光"],
            "适合人设标签": _scene_persona_tags(theme, person_type),
            "差异化备注": f"作为新增核心{theme}场景使用，优先与现有场景形成背景/动作/道具差异。",
            "场景基底_英文": item["场景名称"],
            "风格基调词": f"{theme}，精致生活感，主营类目友好",
            "排除描述": "避免低清晰度、避免道具喧宾夺主、避免重复构图",
            "场景描述_中文": f"围绕{item['场景名称']}搭建画面，突出手机壳/手机链在真实生活中的出现方式。",
            **item,
        }
        ops.append(Operation("scene", "create", code, None, fields))
    return ops


def remediate_persona(records: list[dict]) -> list[Operation]:
    ops: list[Operation] = []
    for record in records:
        fields = record["fields"]
        patch: dict[str, Any] = {}
        tags = _multi_to_list(fields.get("气质标签"))
        scene_tags = _multi_to_list(fields.get("适合场景标签"))
        if tags:
            normalized_tags = [t for t in tags if t in PERSONA_TAGS]
            if normalized_tags and normalized_tags != tags:
                patch["气质标签"] = normalized_tags
        if scene_tags:
            normalized_scene_tags = [t for t in scene_tags if t in SCENE_TAGS]
            if normalized_scene_tags and normalized_scene_tags != scene_tags:
                patch["适合场景标签"] = normalized_scene_tags
        if patch:
            ops.append(Operation(
                table="persona",
                action="update",
                code=_rich_text_to_str(fields.get("人设编号")),
                record_id=record.get("record_id"),
                fields=patch,
            ))

    next_code = _next_code(records, "人设编号", "PS")
    existing_names = _existing_text_set(records, "人设名称")
    next_num = int(re.search(r"(\d+)$", next_code).group(1))
    new_records = [
        {
            "人设名称": "潮流街头手机链女生",
            "性别倾向": "女",
            "年龄段": "22-26",
            "外貌风格": "黑发或挑染短发，街头妆感",
            "穿搭风格": "街头休闲、机能配饰",
            "气质标签": ["甜酷", "松弛"],
            "动作倾向": "走动、甩链、单手持机、侧身回头",
            "适用品类": ["手机链", "手机壳"],
            "适用内容类型": ["穿搭搭配", "种草推荐", "场景展示"],
            "适合场景标签": ["街头", "商场", "咖啡馆"],
            "Prompt描述模板": "Asian girl, 24 years old, trendy streetwear styling, confident and relaxed, phone chain naturally integrated into outfit.",
            "一致性锚点模板": "同一女生，街头短外套+包袋搭配，潮流感手机链出镜，相同面部与发型特征。",
        },
        {
            "人设名称": "送礼向精致女生",
            "性别倾向": "女",
            "年龄段": "22-26",
            "外貌风格": "长卷发，精致淡妆，温柔气质",
            "穿搭风格": "小香风或轻礼服感穿搭",
            "气质标签": ["精致", "甜酷"],
            "动作倾向": "开盒、捧花、递礼物、微笑看镜头",
            "适用品类": ["手机壳", "手机链"],
            "适用内容类型": ["节日/活动限定", "开箱", "好物分享"],
            "适合场景标签": ["礼物", "商场", "居家"],
            "Prompt描述模板": "Asian girl, 24 years old, polished feminine look, gift-unboxing mood, premium and warm expression.",
            "一致性锚点模板": "同一女生，长卷发、精致妆容、礼盒/花束场景，相同面孔特征与服装色系。",
        },
        {
            "人设名称": "极简质感白领女性",
            "性别倾向": "女",
            "年龄段": "26-30",
            "外貌风格": "黑直发，冷白皮，利落职场妆",
            "穿搭风格": "极简通勤、西装或衬衫穿搭",
            "气质标签": ["清冷", "中性简洁"],
            "动作倾向": "刷卡进电梯、单手拿咖啡、边走边看手机",
            "适用品类": ["手机壳", "手机链", "通用"],
            "适用内容类型": ["种草推荐", "场景展示", "好物分享"],
            "适合场景标签": ["通勤", "商场", "咖啡馆"],
            "Prompt描述模板": "Asian woman, 28 years old, minimal office styling, cool-toned professional look, refined and calm.",
            "一致性锚点模板": "同一女性，黑直发、极简职场穿搭、通勤场景，相同面部结构与妆容风格。",
        },
        {
            "人设名称": "中性简洁穿搭人设",
            "性别倾向": "中性",
            "年龄段": "22-26",
            "外貌风格": "短发或中长发，中性清爽妆感",
            "穿搭风格": "黑白灰极简、中性版型",
            "气质标签": ["中性简洁", "清冷"],
            "动作倾向": "自然站立、平视镜头、手持手机走动",
            "适用品类": ["手机壳", "手机链", "通用"],
            "适用内容类型": ["深度测评", "对比测评", "穿搭搭配"],
            "适合场景标签": ["棚拍", "街头", "通勤"],
            "Prompt描述模板": "Androgynous young adult, 24 years old, minimal neutral styling, clean silhouette, modern editorial vibe.",
            "一致性锚点模板": "同一人设，极简中性穿搭、低饱和色系、清爽短发，相同面部轮廓与服装风格。",
        },
    ]
    for item in new_records:
        if item["人设名称"] in existing_names:
            continue
        code = f"PS{next_num:03d}"
        next_num += 1
        fields = {
            "人设编号": code,
            "是否启用": "启用",
            "优先级": 80,
            **item,
        }
        ops.append(Operation("persona", "create", code, None, fields))
    return ops


def build_operations(records_by_table: dict[str, list[dict]]) -> list[Operation]:
    ops: list[Operation] = []
    ops.extend(remediate_strategy(records_by_table["strategy"]))
    ops.extend(remediate_shotplan(records_by_table["shotplan"]))
    ops.extend(remediate_scene(records_by_table["scene"]))
    ops.extend(remediate_persona(records_by_table["persona"]))
    return ops


def apply_operations(client: Any, operations: list[Operation]) -> dict[str, int]:
    summary = {"updated": 0, "created": 0}
    for op in operations:
        if op.action == "update":
            client.update_record(TABLE_IDS[op.table], op.record_id, deepcopy(op.fields))
            summary["updated"] += 1
        elif op.action == "create":
            client.create_record(TABLE_IDS[op.table], deepcopy(op.fields))
            summary["created"] += 1
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--tables", default="strategy,shotplan,scene,persona")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", default=str(REPO_ROOT / "tmp" / "remediation_report.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    unsupported = [t for t in tables if t not in TABLE_IDS]
    if unsupported:
        raise SystemExit(f"Unsupported tables: {unsupported}")

    client = None
    if args.apply:
        missing = [k for k in ["LARK_APP_ID", "LARK_APP_SECRET", "LARK_BASE_TOKEN"] if not os.environ.get(k)]
        if missing:
            raise SystemExit(f"Missing required env vars for --apply: {missing}")
        if FeishuClient is None:
            raise SystemExit("FeishuClient import failed; cannot apply")
        client = FeishuClient(os.environ["LARK_APP_ID"], os.environ["LARK_APP_SECRET"], os.environ["LARK_BASE_TOKEN"])

    records_by_table = {}
    for table in tables:
        records_by_table[table] = _load_records(table, Path(args.export_dir), live=bool(args.apply), client=client)

    selected_records = {
        "strategy": records_by_table.get("strategy", []),
        "shotplan": records_by_table.get("shotplan", []),
        "scene": records_by_table.get("scene", []),
        "persona": records_by_table.get("persona", []),
    }
    operations = build_operations(selected_records)
    operations = [op for op in operations if op.table in tables]

    by_table: dict[str, dict[str, int]] = {}
    for op in operations:
        stats = by_table.setdefault(op.table, {"update": 0, "create": 0})
        stats[op.action] += 1

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "tables": tables,
        "summary": by_table,
        "operations": [
            {
                "table": op.table,
                "action": op.action,
                "code": op.code,
                "record_id": op.record_id,
                "fields": op.fields,
            }
            for op in operations
        ],
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "mode": report["mode"],
        "summary": by_table,
        "report_path": str(report_path),
    }, ensure_ascii=False, indent=2))

    if args.apply and operations:
        apply_summary = apply_operations(client, operations)
        print(json.dumps({"apply_summary": apply_summary}, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
