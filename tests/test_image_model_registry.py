import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'middleware'))

from core.config import load_model_params
from prompt_policies.registry import get_image_model_capability, validate_image_model_capability



def test_registry_returns_reference_first_capability_for_gpt_image2_from_loaded_yaml():
    capability = get_image_model_capability('gpt-image-2', model_params=load_model_params())

    assert capability['prompt_policy'] == 'reference_first'
    assert capability['sub_prompt_identity_lock'] is False
    assert capability['primary_reference_mode'] == 'reference_image'
    assert capability['adapter_family'] == 'openai'
    assert capability['reference_input_mode'] == 'input_image'
    assert capability['generation_size_key'] == 'size'



def test_registry_returns_identity_first_capability_for_nanobanana2_from_loaded_yaml():
    capability = get_image_model_capability('nanobanana-2', model_params=load_model_params())

    assert capability['prompt_policy'] == 'identity_first'
    assert capability['sub_prompt_identity_lock'] is True
    assert capability['primary_reference_mode'] == 'identity_anchor'
    assert capability['adapter_family'] == 'xiaole'
    assert capability['reference_input_mode'] == 'reference_images'
    assert capability['generation_size_key'] == 'aspect_ratio'



def test_registry_can_read_capability_from_model_params_provider_config():
    model_params = {
        'image_model': {
            'providers': {
                'future-reference-model': {
                    'capability': {
                        'prompt_policy': 'reference_first',
                        'sub_prompt_identity_lock': False,
                        'primary_reference_mode': 'reference_image',
                        'adapter_family': 'openai',
                        'reference_input_mode': 'input_image',
                        'generation_size_key': 'size',
                    }
                }
            }
        }
    }

    capability = get_image_model_capability('future-reference-model', model_params=model_params)

    assert capability['prompt_policy'] == 'reference_first'
    assert capability['sub_prompt_identity_lock'] is False
    assert capability['primary_reference_mode'] == 'reference_image'
    assert capability['adapter_family'] == 'openai'
    assert capability['reference_input_mode'] == 'input_image'
    assert capability['generation_size_key'] == 'size'



def test_registry_ignores_incomplete_yaml_capability_and_falls_back_to_defaults():
    model_params = {
        'image_model': {
            'providers': {
                'gpt-image-2': {
                    'capability': {
                        'prompt_policy': 'reference_first',
                        'sub_prompt_identity_lock': False,
                    }
                }
            }
        }
    }

    capability = get_image_model_capability('gpt-image-2', model_params=model_params)

    assert capability['prompt_policy'] == 'identity_first'
    assert capability['sub_prompt_identity_lock'] is True
    assert capability['primary_reference_mode'] == 'identity_anchor'
    assert capability['adapter_family'] == 'generic'
    assert capability['reference_input_mode'] == 'inline_data'
    assert capability['generation_size_key'] == 'image_size'



def test_registry_code_capability_only_acts_as_fallback_when_yaml_missing():
    capability = get_image_model_capability('gpt-image-2', model_params={'image_model': {'providers': {}}})

    assert capability['prompt_policy'] == 'identity_first'
    assert capability['sub_prompt_identity_lock'] is True
    assert capability['primary_reference_mode'] == 'identity_anchor'
    assert capability['adapter_family'] == 'generic'
    assert capability['reference_input_mode'] == 'inline_data'
    assert capability['generation_size_key'] == 'image_size'



def test_registry_ignores_malformed_capability_values_in_model_params():
    model_params = {
        'image_model': {
            'providers': {
                'broken-model': {
                    'capability': 'reference_first',
                }
            }
        }
    }

    capability = get_image_model_capability('broken-model', model_params=model_params)

    assert capability['prompt_policy'] == 'identity_first'
    assert capability['sub_prompt_identity_lock'] is True
    assert capability['primary_reference_mode'] == 'identity_anchor'
    assert capability['adapter_family'] == 'generic'
    assert capability['reference_input_mode'] == 'inline_data'
    assert capability['generation_size_key'] == 'image_size'



def test_registry_ignores_partial_model_params_capability_to_avoid_mixed_runtime_modes():
    model_params = {
        'image_model': {
            'providers': {
                'partial-capability-model': {
                    'capability': {
                        'prompt_policy': 'reference_first',
                    }
                }
            }
        }
    }

    capability = get_image_model_capability('partial-capability-model', model_params=model_params)

    assert capability['prompt_policy'] == 'identity_first'
    assert capability['sub_prompt_identity_lock'] is True
    assert capability['primary_reference_mode'] == 'identity_anchor'
    assert capability['adapter_family'] == 'generic'
    assert capability['reference_input_mode'] == 'inline_data'
    assert capability['generation_size_key'] == 'image_size'



def test_registry_can_read_capability_from_loaded_model_params_yaml():
    model_params = load_model_params()

    capability = get_image_model_capability('gpt-image-2', model_params=model_params)

    assert capability['prompt_policy'] == 'reference_first'
    assert capability['sub_prompt_identity_lock'] is False
    assert capability['primary_reference_mode'] == 'reference_image'
    assert capability['adapter_family'] == 'openai'
    assert capability['reference_input_mode'] == 'input_image'
    assert capability['generation_size_key'] == 'size'



def test_registry_falls_back_to_identity_first_defaults_for_unknown_models():
    capability = get_image_model_capability('some-future-model')

    assert capability['prompt_policy'] == 'identity_first'
    assert capability['sub_prompt_identity_lock'] is True
    assert capability['primary_reference_mode'] == 'identity_anchor'
    assert capability['adapter_family'] == 'generic'
    assert capability['reference_input_mode'] == 'inline_data'
    assert capability['generation_size_key'] == 'image_size'



def test_loaded_image_model_capabilities_are_complete_for_declared_capability_models():
    model_params = load_model_params()
    providers = (model_params.get('image_model') or {}).get('providers') or {}
    capability_models = {
        name: cfg.get('capability')
        for name, cfg in providers.items()
        if isinstance(cfg, dict) and 'capability' in cfg
    }

    assert capability_models, 'expected at least one image_model provider to declare capability'

    for model_name, capability in capability_models.items():
        assert validate_image_model_capability(model_name, capability) == []



def test_validate_image_model_capability_reports_missing_keys():
    errors = validate_image_model_capability('broken-model', {'prompt_policy': 'reference_first'})

    assert errors == [
        "broken-model missing capability keys: ['adapter_family', 'generation_size_key', 'primary_reference_mode', 'reference_input_mode', 'sub_prompt_identity_lock']"
    ]
