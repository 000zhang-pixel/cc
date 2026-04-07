"""
飞书多维表格初始化脚本

用法：
  python scripts/setup_base.py --app-token <BASE_APP_TOKEN>

环境变量：
  LARK_APP_ID      飞书应用 App ID
  LARK_APP_SECRET  飞书应用 App Secret

幂等：已存在的表和字段自动跳过，可安全重复运行。
"""
import argparse
import logging
import os
import sys

# 确保 scripts/ 在 path 中
sys.path.insert(0, os.path.dirname(__file__))

from lib.lark_client import LarkBaseClient
from tables.definitions import TABLES, LINK, LOOKUP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 构建查找引用字段的 property
# ---------------------------------------------------------------------------

def _lookup_property(
    link_field_id: str,
    target_field_id: str,
) -> dict:
    return {
        "formula_expression": "",
        "linked_view_id": "",
        "lookup_field_id": target_field_id,
        "target_field_id": target_field_id,
        "link_field_id": link_field_id,
    }


def _link_property(target_table_id: str) -> dict:
    return {
        "table_id": target_table_id,
        "multiple": True,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def setup(client: LarkBaseClient, app_token: str) -> None:
    # Step 1: 按顺序建表（幂等），收集 name → table_id 映射
    logger.info("=== Step 1: 创建表 ===")
    table_ids: dict[str, str] = {}
    for table_def in TABLES:
        table_name = table_def["name"]
        table_id = client.ensure_table(app_token, table_name)
        table_ids[table_name] = table_id

    # Step 2: 建普通字段（非关联、非引用）
    logger.info("=== Step 2: 创建普通字段 ===")
    for table_def in TABLES:
        table_name = table_def["name"]
        table_id = table_ids[table_name]
        logger.info(f"-- {table_name}")
        for field_def in table_def["fields"]:
            client.ensure_field(app_token, table_id, field_def)

    # Step 3: 建关联字段（type=18），此时所有表已存在
    logger.info("=== Step 3: 创建关联字段 ===")
    # 记录每张表每个关联字段对应的 field_id，供 Step 4 查找引用使用
    link_field_ids: dict[str, dict[str, str]] = {}  # {table_name: {field_name: field_id}}

    for table_def in TABLES:
        table_name = table_def["name"]
        table_id = table_ids[table_name]
        links = table_def.get("links", [])
        if not links:
            continue
        logger.info(f"-- {table_name}")
        link_field_ids[table_name] = {}
        for link in links:
            target_name = link["target_table"]
            if target_name not in table_ids:
                raise RuntimeError(
                    f"关联目标表不存在: {target_name}（请检查建表顺序）"
                )
            field_def = {
                "field_name": link["field_name"],
                "type": LINK,
                "property": _link_property(table_ids[target_name]),
            }
            field_id = client.ensure_field(app_token, table_id, field_def)
            link_field_ids[table_name][link["field_name"]] = field_id

    # Step 4: 建查找引用字段（type=19），依赖 Step 3 的关联字段 ID
    logger.info("=== Step 4: 创建查找引用字段 ===")
    for table_def in TABLES:
        table_name = table_def["name"]
        table_id = table_ids[table_name]
        lookups = table_def.get("lookups", [])
        if not lookups:
            continue
        logger.info(f"-- {table_name}")

        for lk in lookups:
            link_fname = lk["lookup_link_field"]
            # 获取本表关联字段的 field_id
            link_fid = link_field_ids.get(table_name, {}).get(link_fname)
            if not link_fid:
                # 关联字段可能是已跳过的幂等字段，从飞书重新查一次
                existing = client.list_fields(app_token, table_id)
                link_fid = existing.get(link_fname)
            if not link_fid:
                raise RuntimeError(
                    f"找不到关联字段 [{link_fname}]，无法创建查找引用 [{lk['field_name']}]"
                )

            # 获取目标表中目标字段的 field_id
            # 通过关联字段的 property 推断目标表（简化：从 links 配置读）
            target_table_name = next(
                lnk["target_table"]
                for lnk in table_def["links"]
                if lnk["field_name"] == link_fname
            )
            target_table_id = table_ids[target_table_name]
            target_fields = client.list_fields(app_token, target_table_id)
            target_fid = target_fields.get(lk["target_field"])
            if not target_fid:
                raise RuntimeError(
                    f"目标表 [{target_table_name}] 中找不到字段 [{lk['target_field']}]"
                )

            field_def = {
                "field_name": lk["field_name"],
                "type": LOOKUP,
                "property": _lookup_property(link_fid, target_fid),
            }
            client.ensure_field(app_token, table_id, field_def)

    logger.info("=== 全部完成 ===")
    logger.info(f"已初始化 {len(TABLES)} 张表，Base app_token: {app_token}")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="初始化飞书多维表格结构")
    parser.add_argument("--app-token", required=True, help="飞书 Base 的 app_token")
    args = parser.parse_args()

    app_id = os.environ.get("LARK_APP_ID")
    app_secret = os.environ.get("LARK_APP_SECRET")
    if not app_id or not app_secret:
        logger.error("请设置环境变量 LARK_APP_ID 和 LARK_APP_SECRET")
        sys.exit(1)

    client = LarkBaseClient(app_id, app_secret)
    try:
        setup(client, args.app_token)
    except RuntimeError as e:
        logger.error(f"初始化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
