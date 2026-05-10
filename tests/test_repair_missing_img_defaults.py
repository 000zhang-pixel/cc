from pathlib import Path


def test_repair_missing_img_keeps_legacy_nanobanana_fallback_for_missing_plan_image_model():
    script_path = Path(__file__).resolve().parents[1] / 'scripts' / 'repair_missing_img.py'
    source = script_path.read_text(encoding='utf-8')
    assert 'plan_data.get("image_model", "nanobanana-2")' in source
