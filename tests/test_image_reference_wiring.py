import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "middleware"))

from handlers.content_generation import ContentGenerationHandler


class _FakeStorage:
    def get_content_path(self, plan_code, gid):
        return Path("/tmp") / plan_code / gid

    def read_content_meta(self, *args, **kwargs):
        return {}

    def save_content(self, *args, **kwargs):
        return None

    def update_text(self, *args, **kwargs):
        return None

    def update_content_debug(self, *args, **kwargs):
        return None

    def add_file(self, *args, **kwargs):
        return None


class _FakeTextAdapter:
    def complete(self, system_prompt, user_prompt):
        return "【标题】\n标题\n\n【正文】\n正文"


class _FakeImageAdapter:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, ref_images=None):
        self.calls.append({"prompt": prompt, "ref_images": list(ref_images or [])})
        return b"fake-image"


class _FakeFeishu:
    def __init__(self, sku_attachments):
        self.sku_attachments = sku_attachments
        self.downloaded_tokens = []
        self.uploads = []
        self.content_updates = []

    def get_record(self, table_id, record_id):
        if table_id == "plan":
            return {"record_id": record_id, "fields": {"关联SKU": [{"record_ids": ["sku-1"]}]}}
        if table_id == "prompt":
            if record_id == "prompt-c":
                return {"record_id": record_id, "fields": {"总Prompt": "[SYS]\n系统\n[USR]\n文案提示词"}}
            return {
                "record_id": record_id,
                "fields": {
                    "总Prompt": "主图提示词",
                    "子Prompt列表": '["第1张：细节图", "第2张：场景图"]',
                },
            }
        raise AssertionError(f"unexpected get_record({table_id}, {record_id})")

    def get_link_ids(self, record, field_name):
        return ["sku-1"]

    def get_text(self, record, field_name):
        value = record.get("fields", {}).get(field_name, "")
        if isinstance(value, list):
            return value[0] if value else ""
        return "" if value is None else str(value)

    def get_option(self, record, field_name, default=""):
        value = record.get("fields", {}).get(field_name, default)
        if isinstance(value, list):
            return value[0] if value else default
        return value or default

    def list_records(self, table_id, filter_str=None):
        return []

    def create_record(self, table_id, fields):
        return "content-1"

    def update_record(self, table_id, record_id, fields):
        self.content_updates.append((table_id, record_id, fields))

    def download_media(self, file_token):
        self.downloaded_tokens.append(file_token)
        return f"bytes-for-{file_token}".encode("utf-8")

    def upload_attachment(self, table_id, record_id, field_name, file_path, file_name=None):
        self.uploads.append((table_id, record_id, field_name, file_name))
        return f"token-{len(self.uploads)}"


class _NoSequentialImageAdapter(_FakeImageAdapter):
    pass


class _SequentialImageAdapter(_FakeImageAdapter):
    def generate_sequential(self, master_prompt, sub_prompts, ref_images=None):
        return []


def _make_handler(feishu):
    return ContentGenerationHandler(
        feishu,
        {"plan": "plan", "prompt": "prompt", "content": "content"},
        {},
        local_storage=_FakeStorage(),
    )


def _run_generate_content(monkeypatch, image_model_name, image_adapter, sku_attachments, model_params=None):
    from handlers import content_generation as module

    monkeypatch.setattr(module, "build_text_adapter", lambda *args, **kwargs: _FakeTextAdapter())
    monkeypatch.setattr(module, "build_image_adapter", lambda *args, **kwargs: image_adapter)
    monkeypatch.setattr(module.db, "upsert_content", lambda *args, **kwargs: None)
    monkeypatch.setattr(module.db, "update_content_status", lambda *args, **kwargs: None)

    feishu = _FakeFeishu(sku_attachments)
    handler = _make_handler(feishu)
    handler._model_params = model_params or {}
    groups = [{"group_id": "G1", "type": "img", "content_type": "种草推荐", "img_per_piece": 2}]
    prompt_records = [
        {"group": groups[0], "suffix": "C", "prompt_record_id": "prompt-c"},
        {"group": groups[0], "suffix": "I", "prompt_record_id": "prompt-i"},
    ]
    sku_fields = {"白底图": sku_attachments}
    cfg = {
        "task_type": "AI全创作",
        "platforms": ["小红书"],
        "text_model_name": "gpt-5.4",
        "image_model_name": image_model_name,
        "_briefs": {},
        "_persona_assignments": {},
    }

    handler._generate_content(
        groups=groups,
        prompt_records=prompt_records,
        sku_fields=sku_fields,
        cfg=cfg,
        plan_record_id="plan-1",
        tags=[],
    )
    return feishu, image_adapter


def test_generate_content_passes_reference_image_to_gpt_image2_when_white_bg_exists(monkeypatch):
    feishu, adapter = _run_generate_content(
        monkeypatch,
        image_model_name="gpt-image-2",
        image_adapter=_NoSequentialImageAdapter(),
        sku_attachments=[{"file_token": "ft-1"}],
    )

    assert feishu.downloaded_tokens == ["ft-1"]
    assert len(adapter.calls) == 2
    assert adapter.calls[0]["ref_images"] == [b"bytes-for-ft-1"]
    assert adapter.calls[1]["ref_images"] == [b"bytes-for-ft-1"]



def test_generate_content_passes_all_white_bg_images_to_reference_image_mode_model(monkeypatch):
    feishu, adapter = _run_generate_content(
        monkeypatch,
        image_model_name="some-reference-model",
        image_adapter=_SequentialImageAdapter(),
        sku_attachments=[{"file_token": "ft-1"}, {"file_token": "ft-2"}],
        model_params={
            "image_model": {
                "providers": {
                    "some-reference-model": {
                        "capability": {
                            "prompt_policy": "reference_first",
                            "sub_prompt_identity_lock": False,
                            "primary_reference_mode": "reference_image",
                            "adapter_family": "openai",
                            "reference_input_mode": "input_image",
                            "generation_size_key": "size",
                        }
                    }
                }
            }
        },
    )

    assert feishu.downloaded_tokens == ["ft-1", "ft-2"]
    assert len(adapter.calls) == 2
    assert adapter.calls[0]["ref_images"] == [b"bytes-for-ft-1", b"bytes-for-ft-2"]
    assert adapter.calls[1]["ref_images"] == [b"bytes-for-ft-1", b"bytes-for-ft-2"]


def test_generate_content_skips_white_bg_reference_download_for_identity_anchor_mode(monkeypatch):
    feishu, adapter = _run_generate_content(
        monkeypatch,
        image_model_name="some-future-model",
        image_adapter=_SequentialImageAdapter(),
        sku_attachments=[{"file_token": "ft-1"}, {"file_token": "ft-2"}],
        model_params={
            "image_model": {
                "providers": {
                    "some-future-model": {
                        "capability": {
                            "prompt_policy": "identity_first",
                            "sub_prompt_identity_lock": True,
                            "primary_reference_mode": "identity_anchor",
                            "adapter_family": "xiaole",
                            "reference_input_mode": "reference_images",
                            "generation_size_key": "aspect_ratio",
                        }
                    }
                }
            }
        },
    )

    assert feishu.downloaded_tokens == []
    assert len(adapter.calls) == 2
    assert adapter.calls[0]["ref_images"] == []
    assert adapter.calls[1]["ref_images"] == []


def test_generate_content_skips_white_bg_reference_download_for_nanobanana_identity_anchor_mode(monkeypatch):
    feishu, adapter = _run_generate_content(
        monkeypatch,
        image_model_name="nanobanana-2",
        image_adapter=_SequentialImageAdapter(),
        sku_attachments=[{"file_token": "ft-1"}, {"file_token": "ft-2"}],
    )

    assert feishu.downloaded_tokens == []
    assert len(adapter.calls) == 2
    assert adapter.calls[0]["ref_images"] == []
    assert adapter.calls[1]["ref_images"] == []
