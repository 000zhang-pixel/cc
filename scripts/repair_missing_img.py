"""
repair_missing_img.py — 补生成指定任务中缺失的图片。
用法: python repair_missing_img.py T_260417_057 img01 img03
"""
import os, sys, json, time
from pathlib import Path

# Load .env — override=True so updated keys (e.g. NANOBANANA_API_KEY) take effect
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / "middleware" / ".env"
load_dotenv(env_path, override=True)

_repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(_repo_root / "middleware"))
sys.path.insert(0, str(_repo_root))  # for the top-level 'db' package

from adapters.feishu import FeishuClient
from adapters.ai_models import build_image_adapter
from core.local_storage import LocalStorage
from core.config import load_system, load_model_params
from handlers.content_generation import ContentGenerationHandler

# ── Config ────────────────────────────────────────────────────────────────────
sys_cfg   = load_system()       # expands ${ENV_VAR} from .env
model_cfg = load_model_params() # expands ${NANOBANANA_API_KEY} etc.

TABLES = sys_cfg["feishu"]["tables"]
BASE_TOKEN = os.environ["LARK_BASE_TOKEN"]

f = FeishuClient(
    app_id=os.environ["LARK_APP_ID"],
    app_secret=os.environ["LARK_APP_SECRET"],
    base_token=BASE_TOKEN,
)
storage = LocalStorage(Path(os.environ["LOCAL_STORAGE_ROOT"]))
handler = ContentGenerationHandler(feishu=f, tables=TABLES, model_params=model_cfg, local_storage=storage)

# ── Args ──────────────────────────────────────────────────────────────────────
if len(sys.argv) < 3:
    print("Usage: repair_missing_img.py <plan_code> <group_id> [group_id ...]")
    sys.exit(1)

plan_code = sys.argv[1]
group_ids = sys.argv[2:]

# ── Load plan to get image_model ──────────────────────────────────────────────
plan_meta = storage.read_content_meta(plan_code, group_ids[0])
# Fallback: read plan.json directly
plan_json_path = storage.pending / plan_code / "plan.json"
plan_data = json.loads(plan_json_path.read_text(encoding="utf-8"))
image_model_name = plan_data.get("image_model", "nanobanana-2")

img_adapter = build_image_adapter(model_cfg, image_model_name)
is_nanobanana = hasattr(img_adapter, "generate_sequential")
print(f"Image adapter: {image_model_name} (nanobanana={is_nanobanana})")

# ── For each group, find & repair missing images ──────────────────────────────
for gid in group_ids:
    content_code = f"{plan_code}_{gid}"
    print(f"\n{'='*60}")
    print(f"Processing {content_code}")

    # Read content.json to find which images exist
    meta = storage.read_content_meta(plan_code, gid)
    if not meta:
        print(f"  ERROR: content.json not found for {gid}")
        continue

    existing_images = set(meta.get("images") or [])
    img_count = 5  # expected count (hardcoded per task config)

    # Determine which local image files exist on disk
    group_dir = storage.get_content_path(plan_code, gid)
    local_files = {f"img_{idx+1:02d}.jpg" for idx in range(img_count)
                   if (group_dir / f"img_{idx+1:02d}.jpg").exists()}

    # Images missing from disk entirely
    missing_indices = [idx for idx in range(img_count)
                       if f"img_{idx+1:02d}.jpg" not in local_files]

    # Check Feishu record for uploaded attachments count
    content_recs_check = f.list_records(TABLES["content"], filter_str=f'CurrentValue.[内容编号] = "{content_code}"')
    feishu_img_count = 0
    if content_recs_check:
        feishu_attachments = content_recs_check[0]["fields"].get("生成图片") or []
        feishu_img_count = len(feishu_attachments)

    print(f"  Local files ({len(local_files)}): {sorted(local_files)}")
    print(f"  Feishu attachments: {feishu_img_count}")

    # Upload-only: files that exist locally but were NOT in the original content.json images list
    # (i.e., were added by a repair run but Feishu upload failed at that time)
    upload_only_indices = [
        idx for idx in range(img_count)
        if (group_dir / f"img_{idx+1:02d}.jpg").exists()
        and f"img_{idx+1:02d}.jpg" not in existing_images
    ]

    all_repair_indices = sorted(set(missing_indices) | set(upload_only_indices))

    if not all_repair_indices:
        print(f"  All {img_count} images present and uploaded, nothing to do.")
        continue

    if upload_only_indices and not missing_indices:
        print(f"  Local files complete but Feishu only has {feishu_img_count}/{img_count} — re-uploading...")
    else:
        print(f"  Missing indices (0-based): {missing_indices}")

    print(f"  Existing: {sorted(existing_images)}")
    print(f"  Missing indices (0-based): {missing_indices} → {[f'img_{i+1:02d}.jpg' for i in missing_indices]}")

    # Find prompt record from Feishu
    prompt_code = f"P_{plan_code}_{gid}_I"
    recs = f.list_records(TABLES["prompt"], filter_str=f'CurrentValue.[提示词编号] = "{prompt_code}"')
    if not recs:
        print(f"  ERROR: prompt record {prompt_code} not found in Feishu")
        continue

    prompt_rec = recs[0]
    i_prompt_text = f.get_text(prompt_rec, "总Prompt")
    sub_prompts_raw = f.get_text(prompt_rec, "子Prompt列表")
    try:
        sub_prompts = json.loads(sub_prompts_raw) if sub_prompts_raw.strip() else []
    except json.JSONDecodeError:
        sub_prompts = []

    print(f"  Master prompt length: {len(i_prompt_text)} chars, sub_prompts: {len(sub_prompts)}")

    # Pad sub_prompts to img_count if needed
    if not sub_prompts:
        sub_prompts = [i_prompt_text] * img_count
    elif len(sub_prompts) < img_count:
        sub_prompts = (sub_prompts + [sub_prompts[-1]] * img_count)[:img_count]

    # Fetch 白底图 as reference if nanobanana
    ref_images: list[bytes] = []
    if is_nanobanana:
        sku_recs = f.list_records(TABLES["sku"], filter_str=f'CurrentValue.[SKU编号] = "{plan_data["sku_code"]}"')
        if sku_recs:
            bai_di = sku_recs[0]["fields"].get("白底图") or []
            if bai_di:
                first_token = bai_di[0].get("file_token") if isinstance(bai_di[0], dict) else None
                if first_token:
                    try:
                        ref_images = [f.download_media(first_token)]
                        print(f"  Loaded 白底图 reference image")
                    except Exception as exc:
                        print(f"  WARNING: could not load 白底图: {exc}")

    # Find content record in Feishu for attachment upload (moved up for re-upload path)
    if not content_recs_check:
        print(f"  ERROR: content record {content_code} not found in Feishu")
        continue
    content_record_id = content_recs_check[0]["record_id"]

    # Generate/upload each needed image
    for idx in all_repair_indices:
        img_filename = f"img_{idx+1:02d}.jpg"
        local_path = group_dir / img_filename
        try:
            if local_path.exists():
                # Already on disk — just upload to Feishu
                img_bytes = local_path.read_bytes()
                print(f"  {img_filename}: using local file ({len(img_bytes)} bytes), uploading to Feishu...")
            else:
                # Need to generate
                sub_p = sub_prompts[idx]
                print(f"  {img_filename}: generating...")
                if is_nanobanana:
                    combined = f"{i_prompt_text}\n\n---\n\n{sub_p}"
                    img_bytes = img_adapter.generate(combined, ref_images=ref_images or None)
                else:
                    img_bytes = img_adapter.generate(sub_p)
                print(f"  Generated {len(img_bytes)} bytes")
                storage.add_file(plan_code, gid, img_filename, img_bytes)
                print(f"  Saved locally: {img_filename}")

            upload_name = f"{content_code}_img{idx+1:02d}.jpg"
            token = handler._upload_attachment(TABLES["content"], content_record_id, upload_name, img_bytes)
            if token:
                print(f"  Uploaded to Feishu OK (token={token})")
            else:
                print(f"  WARNING: Feishu upload returned no token")

            time.sleep(1)

        except Exception as exc:
            print(f"  ERROR on {img_filename}: {exc}")

    # Update Feishu gen status to 已生成 and clear failure reason
    f.update_record(TABLES["content"], content_record_id, {
        "生成状态": "已生成",
        "失败原因": "",
    })
    print(f"  Feishu record updated → 已生成")

print("\nDone.")
