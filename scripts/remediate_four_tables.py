#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
MIDDLEWARE_ROOT = REPO_ROOT / 'middleware'
load_dotenv(MIDDLEWARE_ROOT / '.env', override=False)
sys.path.insert(0, str(MIDDLEWARE_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from core.config import load_system  # noqa: E402
from adapters.feishu import FeishuClient  # noqa: E402

PLAN_FILE = REPO_ROOT / 'scripts' / 'data' / 'phone_chain_four_table_remediation.json'
CODE_FIELD = {
    'strategy': '策略编号',
    'shotplan': '方案编号',
    'scene': '场景编号',
    'persona': '人设编号',
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Apply four-table remediation plan')
    p.add_argument('--plan-file', default=str(PLAN_FILE))
    p.add_argument('--tables', default='strategy,shotplan,scene,persona')
    p.add_argument(
        '--semantic-actions',
        default='',
        help='Optional comma-separated semantic actions filter (e.g. disable,downgrade,keep,rewrite,add).',
    )
    p.add_argument('--apply', action='store_true', help='Perform live writes. Without this flag, runs dry-run only.')
    p.add_argument('--dry-run', action='store_true', help='Explicitly force dry-run output (default behavior).')
    p.add_argument('--limit', type=int, default=0, help='Only process first N selected operations')
    return p.parse_args()


def load_plan(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def validate_plan(plan: dict, selected_tables: set[str]) -> list[str]:
    errors = []
    ops = plan.get('operations') or []
    seen = set()
    allowed_semantics = {'disable', 'downgrade', 'keep', 'rewrite', 'add'}
    for op in ops:
        key = (op.get('table'), op.get('code'))
        if key in seen:
            errors.append(f'duplicate operation: {key}')
        seen.add(key)
        if op.get('table') not in CODE_FIELD:
            errors.append(f'unsupported table: {op.get("table")}')
        if op.get('table') in selected_tables and not op.get('code'):
            errors.append(f'missing code in selected op: {op}')
        if op.get('action') not in {'update', 'create'}:
            errors.append(f'unsupported action: {op.get("action")} for {key}')
        semantic_action = op.get('semantic_action')
        if semantic_action and semantic_action not in allowed_semantics:
            errors.append(f'unsupported semantic_action: {semantic_action} for {key}')
    return errors


def build_client() -> tuple[FeishuClient, dict[str, str]]:
    sys_cfg = load_system()
    fcfg = sys_cfg['feishu']
    client = FeishuClient(
        app_id=fcfg['app_id'],
        app_secret=fcfg['app_secret'],
        base_token=fcfg['base_token'],
    )
    return client, fcfg['tables']


def lookup_record_id(client: FeishuClient, table_id: str, table_key: str, code: str) -> str:
    code_field = CODE_FIELD[table_key]
    escaped = code.replace('\\', '\\\\').replace('"', '\\"')
    matches = client.list_records(table_id, filter_str=f'CurrentValue.[{code_field}] = "{escaped}"')
    if not matches:
        raise RuntimeError(f'record not found by code: table={table_key} code={code}')
    if len(matches) > 1:
        raise RuntimeError(f'ambiguous code lookup: table={table_key} code={code} matches={len(matches)}')
    return matches[0]['record_id']


def summarize(ops: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for op in ops:
        table = op['table']
        sem = op.get('semantic_action', 'rewrite')
        out.setdefault(table, {'update': 0, 'create': 0, 'semantic': defaultdict(int)})
        out[table][op['action']] += 1
        out[table]['semantic'][sem] += 1
    for table in out:
        out[table]['semantic'] = dict(out[table]['semantic'])
    return out


def parse_csv_set(raw: str) -> set[str]:
    return {x.strip() for x in raw.split(',') if x.strip()}


def main() -> int:
    args = parse_args()
    selected_tables = parse_csv_set(args.tables)
    selected_semantics = parse_csv_set(args.semantic_actions)
    allowed_semantics = {'disable', 'downgrade', 'keep', 'rewrite', 'add'}
    invalid_semantics = sorted(selected_semantics - allowed_semantics)
    if invalid_semantics:
        print(json.dumps({
            'ok': False,
            'phase': 'args',
            'errors': [f'unsupported semantic_actions: {invalid_semantics}'],
        }, ensure_ascii=False, indent=2))
        return 1

    plan = load_plan(Path(args.plan_file))
    ops = [op for op in plan.get('operations', []) if op.get('table') in selected_tables]
    if selected_semantics:
        ops = [op for op in ops if op.get('semantic_action', 'rewrite') in selected_semantics]
    if args.limit > 0:
        ops = ops[:args.limit]

    errors = validate_plan(plan, selected_tables)
    if errors:
        print(json.dumps({'ok': False, 'phase': 'validate', 'errors': errors}, ensure_ascii=False, indent=2))
        return 1

    dry_run = not args.apply or args.dry_run
    payload = {
        'ok': True,
        'mode': 'dry-run' if dry_run else 'apply',
        'plan_file': str(Path(args.plan_file)),
        'selected_tables': sorted(selected_tables),
        'selected_semantic_actions': sorted(selected_semantics),
        'operation_count': len(ops),
        'summary': summarize(ops),
    }

    if dry_run:
        payload['sample'] = [
            {
                'table': op['table'],
                'code': op['code'],
                'action': op['action'],
                'semantic_action': op.get('semantic_action', 'rewrite'),
                'field_count': len(op.get('fields', {})),
            }
            for op in ops[:12]
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    client, tables = build_client()
    results = []
    processed = skipped = failed = 0

    for op in ops:
        table_key = op['table']
        table_id = tables[table_key]
        code = op['code']
        fields = op.get('fields', {})
        result = {
            'table': table_key,
            'code': code,
            'action': op['action'],
            'semantic_action': op.get('semantic_action', 'rewrite'),
        }
        try:
            if op['action'] == 'create':
                existing_id = None
                try:
                    existing_id = lookup_record_id(client, table_id, table_key, code)
                except RuntimeError as exc:
                    if 'record not found by code' not in str(exc):
                        raise
                if existing_id:
                    result.update({'status': 'skipped', 'record_id': existing_id, 'reason': 'already_exists'})
                    skipped += 1
                else:
                    new_id = client.create_record(table_id, fields)
                    result.update({'status': 'applied', 'record_id': new_id})
                    processed += 1
            else:
                record_id = op.get('record_id')
                if not record_id:
                    record_id = lookup_record_id(client, table_id, table_key, code)
                try:
                    client.update_record(table_id, record_id, fields)
                except Exception:
                    # record_id may have drifted; retry by code lookup once
                    record_id = lookup_record_id(client, table_id, table_key, code)
                    client.update_record(table_id, record_id, fields)
                result.update({'status': 'applied', 'record_id': record_id})
                processed += 1
        except Exception as exc:  # noqa: BLE001
            result.update({'status': 'failed', 'error': repr(exc)})
            failed += 1
        results.append(result)

    payload.update({
        'processed': processed,
        'skipped': skipped,
        'failed': failed,
        'results': results,
    })
    payload['ok'] = failed == 0
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if failed == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
