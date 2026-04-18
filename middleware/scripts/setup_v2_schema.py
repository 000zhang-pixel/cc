"""
setup_v2_schema.py — 飞书 Bitable 字段批量创建脚本（Prompt System Upgrade v2）

功能：
1. 为表2/3/4/8/9/10 添加 v2 新增字段（跳过已存在字段）
2. 新建表12 Persona 人设模板表
3. 向表12 录入 12 条初始人设记录

运行：
  cd middleware && python scripts/setup_v2_schema.py
"""
from __future__ import annotations
import sys
import os
import re
import time
import json
from pathlib import Path

# Fix Windows GBK stdout encoding
if sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.config import load_system
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    CreateAppTableFieldRequest,
    AppTableField,
    AppTableFieldProperty,
    AppTableFieldPropertyOption,
    ListAppTableFieldRequest,
    ListAppTableRecordRequest,
    BatchCreateAppTableRequest,
    BatchCreateAppTableRequestBody,
    CreateAppTableRecordRequest,
    AppTableRecord,
    AppTable,
)

# ── 初始化 ────────────────────────────────────────────────────────────────────

cfg = load_system()
f = cfg["feishu"]
APP_TOKEN = f["base_token"]
TABLES = f["tables"]

client = lark.Client.builder() \
    .app_id(f["app_id"]) \
    .app_secret(f["app_secret"]) \
    .log_level(lark.LogLevel.WARNING) \
    .timeout(30) \
    .build()

# ── 字段类型常量 ──────────────────────────────────────────────────────────────

TEXT = 1        # 文本/多行文本
NUMBER = 2      # 数字
SINGLE = 3      # 单选
MULTI = 4       # 多选


def _opt(name: str):
    return AppTableFieldPropertyOption.builder().name(name).build()


def _field(name: str, ftype: int, options: list | None = None) -> AppTableField:
    b = AppTableField.builder().field_name(name).type(ftype)
    if options is not None:
        prop = AppTableFieldProperty.builder().options(options).build()
        b = b.property(prop)
    return b.build()


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def list_existing_fields(table_id: str) -> set[str]:
    """返回已有字段名集合。"""
    names = set()
    page_token = None
    while True:
        rb = (
            ListAppTableFieldRequest.builder()
            .app_token(APP_TOKEN)
            .table_id(table_id)
            .page_size(100)
        )
        if page_token:
            rb = rb.page_token(page_token)
        resp = client.bitable.v1.app_table_field.list(rb.build())
        if not resp.success():
            print(f"  ⚠ list_fields [{resp.code}]: {resp.msg}")
            break
        for item in resp.data.items or []:
            names.add(item.field_name)
        if not resp.data.has_more:
            break
        page_token = resp.data.page_token
    return names


def add_fields(table_label: str, table_id: str, fields: list[AppTableField]):
    """向指定表批量添加字段，跳过已存在的。"""
    print(f"\n{'='*60}")
    print(f"  {table_label}  ({table_id})")
    print(f"{'='*60}")
    existing = list_existing_fields(table_id)
    print(f"  已有字段 {len(existing)} 个")

    added = skipped = failed = 0
    for field in fields:
        if field.field_name in existing:
            print(f"  ⏭ 跳过（已存在）: {field.field_name}")
            skipped += 1
            continue
        req = (
            CreateAppTableFieldRequest.builder()
            .app_token(APP_TOKEN)
            .table_id(table_id)
            .request_body(field)
            .build()
        )
        resp = client.bitable.v1.app_table_field.create(req)
        if resp.success():
            print(f"  ✓ 新增字段: {field.field_name}")
            added += 1
        else:
            print(f"  ✗ 失败 [{resp.code}]: {field.field_name} — {resp.msg}")
            failed += 1
        time.sleep(0.3)  # 避免触发频率限制

    print(f"  → 新增 {added}，跳过 {skipped}，失败 {failed}")


# ── 字段定义 ──────────────────────────────────────────────────────────────────

# 表2 — 内容规划表（plan）
TABLE2_FIELDS = [
    _field("差异化强度", SINGLE, [_opt("低"), _opt("中"), _opt("高")]),
    _field("人设模式",   SINGLE, [_opt("自动"), _opt("固定主人设"), _opt("多人设轮换")]),
    _field("一致性强度", SINGLE, [_opt("中"), _opt("强")]),
    _field("场景丰富度", SINGLE, [_opt("低"), _opt("中"), _opt("高")]),
]

# 表3 — Prompt 记录表（prompt）
TABLE3_FIELDS = [
    _field("创意包摘要",   TEXT),
    _field("创意包JSON",  TEXT),
    _field("命中策略ID",   TEXT),
    _field("命中场景ID",   TEXT),
    _field("命中人设ID",   TEXT),
    _field("命中ShotPlanID", TEXT),
    _field("标题句式",     TEXT),
    _field("叙事角度",     TEXT),
    _field("一致性锚点",   TEXT),
    _field("是否兜底生成", SINGLE, [_opt("是"), _opt("否")]),
]

# 表4 — 内容生成表（content）
TABLE4_FIELDS = [
    _field("创意包摘要",   TEXT),
    _field("命中策略ID",   TEXT),
    _field("命中场景ID",   TEXT),
    _field("命中人设ID",   TEXT),
    _field("命中ShotPlanID", TEXT),
    _field("标题句式",     TEXT),
    _field("叙事角度",     TEXT),
    _field("组内一致性锚点", TEXT),
    _field("图片生成调试信息", TEXT),  # 摘要版: 失败数/序号/Prompt前120字
]

# 表8 — 内容策略表（strategy）
TABLE8_FIELDS = [
    _field("叙事角度标签", MULTI, [
        _opt("搭配点睛"), _opt("日常实用"), _opt("细节质感"),
        _opt("氛围感种草"), _opt("礼物推荐"),
    ]),
    _field("结构模式", SINGLE, [
        _opt("场景切入"), _opt("痛点切入"), _opt("体验切入"),
        _opt("对比切入"), _opt("情绪切入"),
    ]),
    _field("标题句式池",     TEXT),
    _field("正文禁忌",       TEXT),
    _field("差异化提示模板", TEXT),
    _field("人设适配标签",   MULTI, [
        _opt("甜酷"), _opt("清冷"), _opt("松弛"), _opt("精致"), _opt("青春"),
    ]),
]

# 表9 — ShotPlan 拍摄方案表（shotplan）
TABLE9_FIELDS = [
    _field("构图节奏",   SINGLE, [_opt("稳定"), _opt("丰富"), _opt("跳跃")]),
    _field("人物出镜比例", SINGLE, [_opt("无人物"), _opt("少量"), _opt("中等"), _opt("高")]),
    _field("近中远景配比", TEXT),
    _field("道具密度",   SINGLE, [_opt("低"), _opt("中"), _opt("高")]),
    _field("动作变化要求", TEXT),
    _field("禁止重复镜头", TEXT),
]

# 表10 — 场景库（scene）
TABLE10_FIELDS = [
    _field("场景主题", SINGLE, [
        _opt("商场"), _opt("通勤"), _opt("校园"), _opt("居家"),
        _opt("街头"), _opt("咖啡馆"), _opt("户外"),
    ]),
    _field("氛围等级", SINGLE, [_opt("低"), _opt("中"), _opt("高")]),
    _field("道具建议",   TEXT),
    _field("光线风格标签", MULTI, [
        _opt("柔光"), _opt("冷白光"), _opt("暖调"), _opt("背光"), _opt("逆光"),
    ]),
    _field("适合人设标签", MULTI, [
        _opt("甜酷"), _opt("清冷"), _opt("松弛"), _opt("精致"), _opt("青春"),
    ]),
    _field("差异化备注", TEXT),
]

# 表12 — Persona 人设模板表（全新建表）
TABLE12_FIELDS_DEF = [
    _field("人设编号",     TEXT),
    _field("是否启用",     SINGLE, [_opt("启用"), _opt("停用")]),
    _field("人设名称",     TEXT),
    _field("性别倾向",     SINGLE, [_opt("女"), _opt("男"), _opt("中性")]),
    _field("年龄段",       SINGLE, [_opt("18-22"), _opt("22-26"), _opt("26-30"), _opt("30+")]),
    _field("外貌风格",     TEXT),
    _field("穿搭风格",     TEXT),
    _field("气质标签",     MULTI, [
        _opt("甜酷"), _opt("清冷"), _opt("松弛"), _opt("精致"), _opt("青春"),
    ]),
    _field("动作倾向",     TEXT),
    _field("适用品类",     MULTI, [_opt("手机链"), _opt("手机壳"), _opt("通用")]),
    _field("适用内容类型", MULTI, [
        _opt("种草推荐"), _opt("穿搭搭配"), _opt("场景展示"), _opt("开箱测评"),
    ]),
    _field("适合场景标签", MULTI, [
        _opt("商场"), _opt("校园"), _opt("咖啡馆"), _opt("街头"),
        _opt("通勤"), _opt("居家"), _opt("户外"),
    ]),
    _field("Prompt描述模板",   TEXT),
    _field("一致性锚点模板",   TEXT),
    _field("优先级",           NUMBER),
    _field("备注",             TEXT),
]

# 12 条初始人设记录
def _rec(
    code: str, name: str, gender: str, age: str,
    looks: str, style: str, vibes: list[str], action: str,
    cats: list[str], ctypes: list[str], scenes: list[str],
    prompt_tmpl: str, anchor_tmpl: str, priority: int,
) -> dict:
    """Build a persona record with correct Feishu field format:
    - single-select: plain string
    - multi-select: list of plain strings
    """
    return {
        "人设编号":       code,
        "是否启用":       "启用",       # single-select → plain string
        "人设名称":       name,
        "性别倾向":       gender,       # single-select → plain string
        "年龄段":         age,          # single-select → plain string
        "外貌风格":       looks,
        "穿搭风格":       style,
        "气质标签":       vibes,        # multi-select → list of strings
        "动作倾向":       action,
        "适用品类":       cats,         # multi-select → list of strings
        "适用内容类型":   ctypes,       # multi-select → list of strings
        "适合场景标签":   scenes,       # multi-select → list of strings
        "Prompt描述模板": prompt_tmpl,
        "一致性锚点模板": anchor_tmpl,
        "优先级":         priority,
    }


PERSONA_RECORDS = [
    _rec("PS001", "甜酷通勤女生", "女", "22-26",
         "长黑发微卷，轻妆，猫眼眼线", "休闲通勤，微甜oversize",
         ["甜酷"], "自然持握、回头、斜背包",
         ["手机链", "手机壳", "通用"], ["种草推荐", "穿搭搭配"],
         ["商场", "通勤", "街头"],
         "Asian girl, approximately 22 years old, long wavy black hair, light makeup with cat-eye liner, sweet-cool vibe, casual commute style",
         "同一女生，长黑发微卷，轻妆猫眼，甜酷通勤穿搭，同套服装，相同面孔特征", 100),

    _rec("PS002", "清冷文艺女生", "女", "22-26",
         "浅棕直发，无妆感，高级冷白皮", "极简轻奢，米白/黑灰系",
         ["清冷"], "低头看书、单手持机、倚靠",
         ["手机链", "手机壳", "通用"], ["种草推荐", "场景展示"],
         ["咖啡馆", "居家", "校园"],
         "Asian girl, approximately 24 years old, straight light-brown hair, no-makeup look, cold-tone minimalist style, high-end vibe",
         "同一女生，浅棕直发，无妆感冷白皮，极简白黑穿搭，同套服装，相同面孔特征", 95),

    _rec("PS003", "青春校园女生", "女", "18-22",
         "双马尾或丸子头，甜美清纯妆", "学院风，格子/条纹/白衬衫",
         ["青春"], "跑动、抱书、撩发、大笑",
         ["手机链", "手机壳", "通用"], ["种草推荐", "穿搭搭配", "场景展示"],
         ["校园", "街头", "咖啡馆"],
         "Asian girl, approximately 19 years old, twin tails or bun hairstyle, sweet campus style, clean and youthful vibe",
         "同一女生，双马尾/丸子头，甜美清纯妆，学院风穿搭，同套服装，相同面孔特征", 90),

    _rec("PS004", "精致都市白领", "女", "26-30",
         "黑直发或鲍勃，精致职场妆", "OL职场，西装/衬衫/裙摆",
         ["精致"], "端咖啡、低头看手机、走动",
         ["手机链", "手机壳", "通用"], ["种草推荐", "场景展示"],
         ["通勤", "商场", "咖啡馆"],
         "Asian girl, approximately 27 years old, sleek bob or straight black hair, polished office makeup, professional yet stylish",
         "同一女生，鲍勃/直发，精致职场妆，OL穿搭，同套服装，相同面孔特征", 88),

    _rec("PS005", "松弛户外女孩", "女", "22-26",
         "随意马尾或抓发，自然素颜感", "运动休闲，卫衣/工装/帽子",
         ["松弛"], "走动、拉伸、仰头、随意挎包",
         ["手机链", "通用"], ["种草推荐", "场景展示"],
         ["户外", "街头", "通勤"],
         "Asian girl, approximately 23 years old, casual ponytail or messy bun, natural no-fuss look, sporty relaxed vibe",
         "同一女生，随意马尾，素颜自然感，运动休闲穿搭，同套服装，相同面孔特征", 85),

    _rec("PS006", "时髦街拍女孩", "女", "22-26",
         "短发或蓬松中分，大气欧美妆", "街头时尚，皮夹克/宽腿裤/马丁靴",
         ["精致"], "回头、侧身、撩发、手插口袋",
         ["手机链", "手机壳", "通用"], ["种草推荐", "穿搭搭配"],
         ["街头", "商场", "户外"],
         "Asian girl, approximately 25 years old, bold short hair or voluminous parted style, statement makeup, street fashion vibe",
         "同一女生，短发/中分蓬松，欧美妆容，街头时尚穿搭，同套服装，相同面孔特征", 82),

    _rec("PS007", "甜美软妹女生", "女", "18-22",
         "自然卷/内扣发，粉嫩少女妆", "甜美少女，粉色/花裙/蝴蝶结",
         ["甜酷", "青春"], "捧脸、托腮、双手持机、微笑",
         ["手机链", "手机壳", "通用"], ["种草推荐", "穿搭搭配"],
         ["居家", "校园", "咖啡馆"],
         "Asian girl, approximately 20 years old, natural curls or C-curl hair, soft pink makeup, sweet girly style with bows and pastels",
         "同一女生，自然卷/内扣发，粉嫩少女妆，甜美粉色穿搭，同套服装，相同面孔特征", 80),

    _rec("PS008", "知性学霸女生", "女", "18-22",
         "黑直发马尾或半扎，斯文感", "学院风，条纹衬衫/针织开衫",
         ["清冷", "青春"], "低头看书、侧身看远处、单手持机",
         ["手机链", "手机壳", "通用"], ["种草推荐", "场景展示"],
         ["校园", "咖啡馆", "居家"],
         "Asian girl, approximately 21 years old, neat straight black hair in ponytail or half-up, scholarly elegant look, preppy academic style",
         "同一女生，黑直发马尾，知性斯文妆，学院条纹穿搭，同套服装，相同面孔特征", 78),

    _rec("PS009", "复古港风女生", "女", "26-30",
         "微卷中发，复古红唇，高级感", "港风复古，格纹西装/旗袍改良/复古印花",
         ["精致"], "侧身回眸、撑下巴、斜靠墙",
         ["手机链", "手机壳", "通用"], ["种草推荐", "穿搭搭配"],
         ["商场", "街头", "咖啡馆"],
         "Asian girl, approximately 26 years old, slightly wavy mid-length hair, retro red lip, Hong Kong vintage glamour",
         "同一女生，微卷中发，复古红唇妆，港风格纹穿搭，同套服装，相同面孔特征", 75),

    _rec("PS010", "奶油韩系女生", "女", "18-22",
         "柔顺直发/空气刘海，韩式奶油妆", "奶油系，米色/奶白/浅粉系针织/大衣",
         ["青春", "甜酷"], "单手捧脸、低头微笑、轻握手机",
         ["手机链", "手机壳", "通用"], ["种草推荐", "穿搭搭配"],
         ["咖啡馆", "居家", "商场"],
         "Asian girl, approximately 21 years old, silky straight hair with wispy bangs, Korean creamy soft makeup, muted pastel tones",
         "同一女生，柔顺直发空气刘海，韩系奶油妆，奶油色系穿搭，同套服装，相同面孔特征", 72),

    _rec("PS011", "中性穿搭女生", "中性", "22-26",
         "短发或帽子压发，自然淡妆", "中性休闲，帽衫/工装裤/板鞋",
         ["松弛"], "手插口袋、低头看手机、随意站立",
         ["手机链", "通用"], ["种草推荐", "场景展示"],
         ["街头", "户外", "通勤"],
         "Asian girl, approximately 23 years old, short hair or baseball cap, natural light makeup, androgynous casual vibe",
         "同一女生，短发/帽子压发，自然淡妆，中性工装穿搭，同套服装，相同面孔特征", 68),

    _rec("PS012", "氛围感摄影女孩", "女", "22-26",
         "蓬松波浪发，迷离慵懒感，微烟熏", "慵懒欧美，皮草/薄纱/单色宽松系",
         ["清冷", "松弛"], "仰头、斜靠、侧脸对光、半遮脸",
         ["手机链", "手机壳", "通用"], ["种草推荐", "场景展示"],
         ["户外", "居家", "街头"],
         "Asian girl, approximately 25 years old, loose wavy hair, dreamy smoky eye makeup, ethereal moody fashion sense",
         "同一女生，蓬松波浪发，微烟熏慵懒妆，氛围感单色穿搭，同套服装，相同面孔特征", 65),
]


# ── 创建表12 并录入数据 ───────────────────────────────────────────────────────

def create_persona_table() -> str | None:
    """创建表12 Persona 人设模板表，返回 table_id。"""
    print("\n" + "="*60)
    print("  创建表12 — Persona 人设模板表")
    print("="*60)

    from lark_oapi.api.bitable.v1 import (
        BatchCreateAppTableRequest,
        BatchCreateAppTableRequestBody,
        ReqTable,
    )

    req_table = ReqTable.builder().name("Persona 人设模板").build()
    body = BatchCreateAppTableRequestBody.builder().tables([req_table]).build()
    req = (
        BatchCreateAppTableRequest.builder()
        .app_token(APP_TOKEN)
        .request_body(body)
        .build()
    )
    resp = client.bitable.v1.app_table.batch_create(req)
    if not resp.success():
        print(f"  ✗ 建表失败 [{resp.code}]: {resp.msg}")
        return None

    table_id = resp.data.table_ids[0]
    print(f"  ✓ 建表成功，table_id = {table_id}")
    return table_id


def setup_persona_table_fields(table_id: str):
    """为表12 创建 16 个字段（第一个字段名默认已存在，从第2个开始）。"""
    # 飞书新建表自带一个默认"文本"字段，我们先列出已有字段
    existing = list_existing_fields(table_id)
    print(f"  已有字段: {existing}")

    # 如果已有"文本"字段，先重命名为"人设编号"
    from lark_oapi.api.bitable.v1 import (
        ListAppTableFieldRequest,
        UpdateAppTableFieldRequest,
    )

    # 列出字段拿到默认字段ID
    rb = (
        ListAppTableFieldRequest.builder()
        .app_token(APP_TOKEN)
        .table_id(table_id)
        .page_size(100)
        .build()
    )
    resp = client.bitable.v1.app_table_field.list(rb)
    default_field_id = None
    default_field_name = None
    if resp.success() and resp.data.items:
        default_field_id = resp.data.items[0].field_id
        default_field_name = resp.data.items[0].field_name

    if default_field_id and default_field_name != "人设编号":
        update_field = AppTableField.builder().field_name("人设编号").type(TEXT).build()
        ureq = (
            UpdateAppTableFieldRequest.builder()
            .app_token(APP_TOKEN)
            .table_id(table_id)
            .field_id(default_field_id)
            .request_body(update_field)
            .build()
        )
        uresp = client.bitable.v1.app_table_field.update(ureq)
        if uresp.success():
            print(f"  ✓ 重命名默认字段 → 人设编号")
        existing.discard(default_field_name)
        existing.add("人设编号")

    # 依次创建剩余字段
    added = skipped = failed = 0
    for field in TABLE12_FIELDS_DEF:
        if field.field_name in existing:
            print(f"  ⏭ 跳过（已存在）: {field.field_name}")
            skipped += 1
            continue
        req = (
            CreateAppTableFieldRequest.builder()
            .app_token(APP_TOKEN)
            .table_id(table_id)
            .request_body(field)
            .build()
        )
        r = client.bitable.v1.app_table_field.create(req)
        if r.success():
            print(f"  ✓ 新增字段: {field.field_name}")
            added += 1
        else:
            print(f"  ✗ 失败 [{r.code}]: {field.field_name} — {r.msg}")
            failed += 1
        time.sleep(0.3)

    print(f"  → 新增 {added}，跳过 {skipped}，失败 {failed}")


def count_persona_records(table_id: str) -> int:
    """Return 0 if the table has no records, 1 if it has at least one.
    Returns -1 on API error (treat as non-empty to avoid accidental re-seed)."""
    rb = (
        ListAppTableRecordRequest.builder()
        .app_token(APP_TOKEN)
        .table_id(table_id)
        .page_size(1)
        .build()
    )
    resp = client.bitable.v1.app_table_record.list(rb)
    if not resp.success():
        print(f"  ⚠ count_records [{resp.code}]: {resp.msg}")
        return -1
    return 1 if (resp.data.items or []) else 0


def insert_persona_records(table_id: str):
    """录入 12 条初始人设记录。"""
    print(f"\n  录入 {len(PERSONA_RECORDS)} 条人设记录...")
    added = failed = 0
    for rec in PERSONA_RECORDS:
        fields = {}
        for k, v in rec.items():
            fields[k] = v  # plain str / int / list[str] — exactly what Feishu expects

        record = AppTableRecord.builder().fields(fields).build()
        req = (
            CreateAppTableRecordRequest.builder()
            .app_token(APP_TOKEN)
            .table_id(table_id)
            .request_body(record)
            .build()
        )
        resp = client.bitable.v1.app_table_record.create(req)
        if resp.success():
            print(f"  ✓ 录入: {rec['人设编号']} {rec['人设名称']}")
            added += 1
        else:
            print(f"  ✗ 失败 [{resp.code}]: {rec['人设编号']} — {resp.msg}")
            failed += 1
        time.sleep(0.3)
    print(f"  → 录入成功 {added}，失败 {failed}")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  飞书 Bitable 字段创建脚本 — Prompt System Upgrade v2")
    print("=" * 60)
    print(f"  Base: {APP_TOKEN[:10]}...")
    print()

    # 1. 更新现有表字段
    add_fields("表2 — 内容规划表 (plan)",     TABLES["plan"],     TABLE2_FIELDS)
    add_fields("表3 — Prompt记录表 (prompt)",  TABLES["prompt"],   TABLE3_FIELDS)
    add_fields("表4 — 内容生成表 (content)",   TABLES["content"],  TABLE4_FIELDS)
    add_fields("表8 — 内容策略表 (strategy)",  TABLES["strategy"], TABLE8_FIELDS)
    add_fields("表9 — ShotPlan (shotplan)",    TABLES["shotplan"], TABLE9_FIELDS)
    add_fields("表10 — 场景库 (scene)",        TABLES["scene"],    TABLE10_FIELDS)

    # 2. 创建/检查表12
    # Fix: use repo-relative path so script works on any machine / directory layout
    _yaml_path = Path(__file__).resolve().parents[1] / "config" / "system.yaml"

    persona_table_id = TABLES.get("persona", "")
    if persona_table_id:
        print(f"\n  表12 已配置 table_id={persona_table_id}，跳过建表，直接补字段")
        setup_persona_table_fields(persona_table_id)
        # Auto-seed: if table exists but has no records, write initial persona data
        record_count = count_persona_records(persona_table_id)
        if record_count == 0:
            print("  表12 记录为空，自动录入初始人设数据...")
            time.sleep(0.5)
            insert_persona_records(persona_table_id)
        elif record_count > 0:
            print(f"  表12 已有记录，跳过 seed 录入")
        else:
            print("  表12 记录数检查失败，跳过 seed 录入（保守策略）")
    else:
        persona_table_id = create_persona_table()
        if persona_table_id:
            time.sleep(1)
            setup_persona_table_fields(persona_table_id)
            time.sleep(0.5)
            insert_persona_records(persona_table_id)

            # 3. 写回 system.yaml（repo-relative path）
            with open(_yaml_path, encoding="utf-8") as f_:
                content = f_.read()
            # Use regex to tolerate any whitespace/quote variation around the empty value
            new_content, n_subs = re.subn(
                r'(persona:\s*)(["\']?\s*["\']?)\s*$',
                rf'\g<1>{persona_table_id}',
                content,
                flags=re.MULTILINE,
            )
            if n_subs == 0:
                print(f"\n  ⚠ system.yaml 中未找到空 persona 条目，请手动更新 persona: {persona_table_id}")
            else:
                with open(_yaml_path, "w", encoding="utf-8") as f_:
                    f_.write(new_content)
                print(f"\n  ✓ system.yaml 已更新 persona: {persona_table_id}")
        else:
            print("\n  ✗ 建表失败，跳过人设录入")

    print("\n" + "="*60)
    print("  全部完成！请刷新飞书多维表格查看新字段。")
    print("="*60)


if __name__ == "__main__":
    main()
