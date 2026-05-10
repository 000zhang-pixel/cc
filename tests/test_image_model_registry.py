import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'middleware'))

from prompt_policies.registry import get_image_model_capability


def test_registry_returns_reference_first_capability_for_gpt_image2():
    capability = get_image_model_capability('gpt-image-2')

    assert capability['prompt_policy'] == 'reference_first'
    assert capability['sub_prompt_identity_lock'] is False
    assert capability['primary_reference_mode'] == 'reference_image'


def test_registry_returns_identity_first_capability_for_nanobanana2():
    capability = get_image_model_capability('nanobanana-2')

    assert capability['prompt_policy'] == 'identity_first'
    assert capability['sub_prompt_identity_lock'] is True
    assert capability['primary_reference_mode'] == 'identity_anchor'


def test_registry_falls_back_to_identity_first_defaults_for_unknown_models():
    capability = get_image_model_capability('some-future-model')

    assert capability['prompt_policy'] == 'identity_first'
    assert capability['sub_prompt_identity_lock'] is True
    assert capability['primary_reference_mode'] == 'identity_anchor'
