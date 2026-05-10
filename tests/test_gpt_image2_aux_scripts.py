from pathlib import Path


def test_repair_missing_img_keeps_legacy_nanobanana_fallback_for_missing_plan_image_model():
    script = Path('/Users/carson/workspace/ai-content-hub/scripts/repair_missing_img.py').read_text(encoding='utf-8')

    assert 'plan_data.get("image_model", "nanobanana-2")' in script


def test_reset_plan_usage_examples_default_to_gpt_image2():
    script = Path('/Users/carson/workspace/ai-content-hub/scripts/reset_plan.py').read_text(encoding='utf-8')

    assert '--image-model gpt-image-2' in script
