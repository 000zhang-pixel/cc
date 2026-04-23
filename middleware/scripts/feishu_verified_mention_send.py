#!/usr/bin/env python3
"""Send Feishu messages with mandatory real-mention verification.

Purpose:
- resolve target mention from a checked-in registry instead of guessed display names
- send using app identity by default
- read the message back immediately
- fail fast unless sender/body/mentions all match expected values
- support sender-specific compatible mention objects when Feishu resolves the same
  display name to different directory objects for different app senders
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
MIDDLEWARE_ROOT = REPO_ROOT / "middleware"
DEFAULT_ENV_PATH = MIDDLEWARE_ROOT / ".env"
REGISTRY_PATH = MIDDLEWARE_ROOT / "config" / "feishu_mention_registry.json"


class VerificationError(RuntimeError):
    """Raised when the sent message fails mention verification."""


@dataclass(frozen=True)
class MentionTarget:
    role_name: str
    canonical_open_id: str
    display_name: str
    aliases: tuple[str, ...]
    evidence_message_id: str | None
    compatible_open_ids_by_sender: dict[str, tuple[str, ...]]

    def allowed_open_ids_for_sender(self, sender_key: str) -> tuple[str, ...]:
        sender_specific = self.compatible_open_ids_by_sender.get(sender_key) or ()
        merged: list[str] = []
        for open_id in (self.canonical_open_id, *sender_specific):
            if open_id and open_id not in merged:
                merged.append(open_id)
        return tuple(merged)


@dataclass(frozen=True)
class ChatTarget:
    key: str
    name: str
    chat_id: str


@dataclass(frozen=True)
class SenderIdentity:
    key: str
    display_name: str
    sender_id: str
    sender_type: str
    env_path: str | None = None


@dataclass(frozen=True)
class Registry:
    chats: dict[str, ChatTarget]
    identities: dict[str, SenderIdentity]
    targets: dict[str, MentionTarget]


@dataclass(frozen=True)
class RuntimeEnv:
    default_env_path: str
    active_env_path: str


def render_mention(target: MentionTarget) -> str:
    return f'<at user_id="{target.canonical_open_id}">{target.display_name}</at>'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Feishu message with mandatory mention verification")
    parser.add_argument("--label", required=True, help="workflow label, e.g. 接单/进展/风险/交付")
    parser.add_argument("--target", required=True, help="primary target role/display name as defined in registry")
    parser.add_argument("--next-owner", action="append", default=[], help="additional target(s) that must be real-mentioned as next owner / handoff target; repeatable")
    parser.add_argument("--text", required=True, help="message body after the mention")
    parser.add_argument("--chat", default="hermes_board", help="chat key in registry (default: hermes_board)")
    parser.add_argument("--identity", default="it_agent_app", help="sender identity key in registry")
    parser.add_argument("--registry", default=str(REGISTRY_PATH), help="path to mention registry json")
    parser.add_argument("--receive-id-type", default="chat_id", choices=["chat_id"], help="Feishu receive_id_type")
    parser.add_argument("--dry-run", action="store_true", help="print resolved payload and skip send")
    parser.add_argument(
        "--verify-message-id",
        help="skip send; verify an existing message id against the expected target/chat/sender rules",
    )
    parser.add_argument(
        "--allow-alias-name",
        action="store_true",
        help="accept mention name matching an alias in registry; default requires current display_name exact match",
    )
    return parser.parse_args()


def load_registry(path: str) -> Registry:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    chats = {
        key: ChatTarget(key=key, name=value["name"], chat_id=value["chat_id"])
        for key, value in raw.get("chats", {}).items()
    }
    identities = {
        key: SenderIdentity(
            key=key,
            display_name=value["display_name"],
            sender_id=value["sender_id"],
            sender_type=value["sender_type"],
            env_path=value.get("env_path"),
        )
        for key, value in raw.get("identities", {}).items()
    }
    targets = {}
    for key, value in raw.get("targets", {}).items():
        canonical_open_id = value.get("canonical_open_id") or value.get("open_id")
        compatible_open_ids_by_sender = {
            sender_key: tuple(ids)
            for sender_key, ids in (value.get("compatible_open_ids_by_sender") or {}).items()
        }
        targets[key] = MentionTarget(
            role_name=key,
            canonical_open_id=canonical_open_id,
            display_name=value["display_name"],
            aliases=tuple(value.get("aliases", [])),
            evidence_message_id=value.get("evidence_message_id"),
            compatible_open_ids_by_sender=compatible_open_ids_by_sender,
        )
    return Registry(chats=chats, identities=identities, targets=targets)


def require_env(name: str, *aliases: str) -> str:
    for key in (name, *aliases):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    alias_note = f" (aliases: {', '.join(aliases)})" if aliases else ""
    raise RuntimeError(f"Missing required env var: {name}{alias_note}")


def resolve_env_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def load_runtime_env(sender_identity: SenderIdentity) -> RuntimeEnv:
    load_dotenv(DEFAULT_ENV_PATH, override=False)
    active_path = DEFAULT_ENV_PATH
    sender_env_path = resolve_env_path(sender_identity.env_path)
    if sender_env_path:
        if not sender_env_path.exists():
            raise RuntimeError(f"Configured env_path does not exist for {sender_identity.key}: {sender_env_path}")
        load_dotenv(sender_env_path, override=True)
        active_path = sender_env_path
    return RuntimeEnv(default_env_path=str(DEFAULT_ENV_PATH), active_env_path=str(active_path))


def http_json(method: str, url: str, *, token: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {error_body}") from exc
    return json.loads(body)


def get_tenant_access_token() -> str:
    app_id = require_env("FEISHU_APP_ID", "LARK_APP_ID")
    app_secret = require_env("FEISHU_APP_SECRET", "LARK_APP_SECRET")
    resp = http_json(
        "POST",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        payload={"app_id": app_id, "app_secret": app_secret},
    )
    if resp.get("code") != 0:
        raise RuntimeError(f"Failed to get tenant access token: {resp}")
    token = (resp.get("tenant_access_token") or "").strip()
    if not token:
        raise RuntimeError(f"Missing tenant_access_token in response: {resp}")
    return token


def resolve_target(registry: Registry, requested: str) -> MentionTarget:
    if requested in registry.targets:
        return registry.targets[requested]
    for target in registry.targets.values():
        if requested == target.display_name or requested in target.aliases:
            return target
    raise KeyError(f"Target {requested!r} not found in registry")


def build_text(label: str, target: MentionTarget, text: str, next_owners: list[MentionTarget] | None = None) -> str:
    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("--text cannot be empty")
    prefix = f"【{label.strip()}】{render_mention(target)}"
    suffix = ""
    if next_owners:
        owner_mentions = "、".join(render_mention(owner) for owner in next_owners)
        suffix = f" 下一责任人：{owner_mentions}。"
    return f"{prefix} {normalized_text}{suffix}"


def send_message(token: str, chat: ChatTarget, text: str) -> dict[str, Any]:
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    payload = {
        "receive_id": chat.chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    return http_json("POST", url, token=token, payload=payload)


def get_message(token: str, message_id: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(message_id, safe="")
    return http_json("GET", f"https://open.feishu.cn/open-apis/im/v1/messages/{encoded}", token=token)


def unwrap_message_data(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("message_id"), str):
        return payload
    items = payload.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return payload


def extract_mentions(message_data: dict[str, Any]) -> list[dict[str, Any]]:
    items = message_data.get("mentions")
    return items if isinstance(items, list) else []


def extract_sender(message_data: dict[str, Any]) -> dict[str, Any]:
    sender = message_data.get("sender")
    return sender if isinstance(sender, dict) else {}


def _extract_open_id(raw: Any) -> str | None:
    if isinstance(raw, dict):
        return raw.get("open_id") or raw.get("id")
    if isinstance(raw, str):
        return raw
    return None


def verify_message(
    message_data: dict[str, Any],
    *,
    chat: ChatTarget,
    sender_identity: SenderIdentity,
    target: MentionTarget,
    next_owners: list[MentionTarget],
    allow_alias_name: bool,
) -> dict[str, Any]:
    message_data = unwrap_message_data(message_data)
    sender = extract_sender(message_data)
    sender_id = _extract_open_id(sender.get("id")) or sender.get("id")
    sender_type = sender.get("sender_type")
    body = message_data.get("body") if isinstance(message_data.get("body"), dict) else {}
    body_content = body.get("content", "")
    mentions = extract_mentions(message_data)
    mention_names = [item.get("name") for item in mentions if isinstance(item, dict)]
    mention_ids = [_extract_open_id(item.get("id")) for item in mentions if isinstance(item, dict)]
    mention_ids = [item for item in mention_ids if item]

    required_targets = [target, *next_owners]
    target_checks = []
    actual_mention_open_id = None
    compat_mode = False
    for index, required_target in enumerate(required_targets):
        acceptable_names = {required_target.display_name}
        if allow_alias_name:
            acceptable_names.update(required_target.aliases)
        allowed_open_ids = list(required_target.allowed_open_ids_for_sender(sender_identity.key))
        mention_id_match = any(open_id in mention_ids for open_id in allowed_open_ids)
        canonical_match = required_target.canonical_open_id in mention_ids
        actual_match = next((open_id for open_id in mention_ids if open_id in allowed_open_ids), None)
        if index == 0:
            actual_mention_open_id = actual_match
            compat_mode = bool(mention_id_match and not canonical_match)
        target_checks.append(
            {
                "role_name": required_target.role_name,
                "display_name": required_target.display_name,
                "canonical_open_id": required_target.canonical_open_id,
                "allowed_open_ids_for_sender": allowed_open_ids,
                "mention_id_match": mention_id_match,
                "mention_name_match": any(name in acceptable_names for name in mention_names),
                "canonical_match": canonical_match,
                "actual_mention_open_id": actual_match,
                "is_primary": index == 0,
            }
        )

    primary_check = target_checks[0]
    next_owner_checks = target_checks[1:]
    all_required_mentions_match = all(
        item["mention_id_match"] and item["mention_name_match"] for item in target_checks
    )

    checks = {
        "chat_match": message_data.get("chat_id") == chat.chat_id,
        "sender_type_match": sender_type == sender_identity.sender_type,
        "sender_id_match": sender_id == sender_identity.sender_id,
        "body_has_placeholder": "@_user_" in body_content,
        "mentions_non_empty": bool(mentions),
        "mention_id_match": primary_check["mention_id_match"],
        "mention_name_match": primary_check["mention_name_match"],
        "canonical_match": primary_check["canonical_match"],
        "all_required_mentions_match": all_required_mentions_match,
    }
    ok = all(v for k, v in checks.items() if k != "canonical_match")
    result = {
        "ok": ok,
        "checks": checks,
        "message_id": message_data.get("message_id"),
        "chat_id": message_data.get("chat_id"),
        "sender_type": sender_type,
        "sender_id": sender_id,
        "body_content": body_content,
        "mention_names": mention_names,
        "mention_ids": mention_ids,
        "actual_mention_open_id": actual_mention_open_id,
        "compat_mode": compat_mode,
        "target_checks": target_checks,
        "expected": {
            "chat_id": chat.chat_id,
            "sender_type": sender_identity.sender_type,
            "sender_id": sender_identity.sender_id,
            "target_open_id": target.canonical_open_id,
            "target_display_name": target.display_name,
            "target_aliases": list(target.aliases),
            "canonical_open_id": target.canonical_open_id,
            "allowed_open_ids_for_sender": primary_check["allowed_open_ids_for_sender"],
            "next_owner_display_names": [item["display_name"] for item in next_owner_checks],
            "next_owner_open_ids": [item["canonical_open_id"] for item in next_owner_checks],
            "required_targets": [
                {
                    "role_name": item["role_name"],
                    "display_name": item["display_name"],
                    "canonical_open_id": item["canonical_open_id"],
                    "allowed_open_ids_for_sender": item["allowed_open_ids_for_sender"],
                    "is_primary": item["is_primary"],
                }
                for item in target_checks
            ],
        },
    }
    if not ok:
        raise VerificationError(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    args = parse_args()
    registry = load_registry(args.registry)
    chat = registry.chats.get(args.chat)
    if not chat:
        raise KeyError(f"Chat {args.chat!r} not found in registry")
    sender_identity = registry.identities.get(args.identity)
    if not sender_identity:
        raise KeyError(f"Identity {args.identity!r} not found in registry")
    runtime_env = load_runtime_env(sender_identity)
    target = resolve_target(registry, args.target)
    next_owners = [resolve_target(registry, requested) for requested in args.next_owner]
    text = build_text(args.label, target, args.text, next_owners)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "chat": chat.__dict__,
                    "sender_identity": sender_identity.__dict__,
                    "runtime_env": runtime_env.__dict__,
                    "target": {
                        **target.__dict__,
                        "allowed_open_ids_for_sender": list(target.allowed_open_ids_for_sender(sender_identity.key)),
                    },
                    "next_owners": [
                        {
                            **owner.__dict__,
                            "allowed_open_ids_for_sender": list(owner.allowed_open_ids_for_sender(sender_identity.key)),
                        }
                        for owner in next_owners
                    ],
                    "rendered_text": text,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    token = get_tenant_access_token()

    if args.verify_message_id:
        message_resp = get_message(token, args.verify_message_id)
        if message_resp.get("code") != 0:
            raise RuntimeError(f"Failed to fetch message: {message_resp}")
        result = verify_message(
            message_resp.get("data") or {},
            chat=chat,
            sender_identity=sender_identity,
            target=target,
            next_owners=next_owners,
            allow_alias_name=args.allow_alias_name,
        )
        print(json.dumps({"mode": "verify_existing", "runtime_env": runtime_env.__dict__, **result}, ensure_ascii=False, indent=2))
        return 0

    send_resp = send_message(token, chat, text)
    if send_resp.get("code") != 0:
        raise RuntimeError(f"Failed to send message: {send_resp}")
    message_id = ((send_resp.get("data") or {}).get("message_id") or "").strip()
    if not message_id:
        raise RuntimeError(f"Send succeeded but message_id missing: {send_resp}")

    message_resp = get_message(token, message_id)
    if message_resp.get("code") != 0:
        raise RuntimeError(f"Failed to fetch sent message: {message_resp}")
    result = verify_message(
        message_resp.get("data") or {},
        chat=chat,
        sender_identity=sender_identity,
        target=target,
        next_owners=next_owners,
        allow_alias_name=args.allow_alias_name,
    )
    print(json.dumps({"mode": "send_and_verify", "runtime_env": runtime_env.__dict__, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
