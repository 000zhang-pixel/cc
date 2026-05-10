import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'middleware'))

from adapters.ai_models import (
    OpenAIImageAdapter,
    XiaoleImageAdapter,
    ImageModelAdapter,
    build_image_adapter,
)


def _image_model_root(providers: dict) -> dict:
    return {
        'image_model': {
            'max_concurrency': 2,
            'retry_max': 1,
            'retry_base_seconds': 1,
            'providers': providers,
        }
    }



def test_build_image_adapter_can_route_openai_family_from_capability():
    model_params = _image_model_root({
        'future-openai-model': {
            'api_key': 'test-key',
            'base_url': 'https://api.example.com/v1',
            'model': 'gpt-5.5',
            'image_model': 'gpt-image-2',
            'generation_size': '1024x1536',
            'capability': {
                'prompt_policy': 'reference_first',
                'sub_prompt_identity_lock': False,
                'primary_reference_mode': 'reference_image',
                'adapter_family': 'openai',
                'reference_input_mode': 'input_image',
                'generation_size_key': 'size',
            },
        }
    })

    adapter = build_image_adapter(model_params, 'future-openai-model')

    assert isinstance(adapter, OpenAIImageAdapter)
    assert adapter._size == '1024x1536'



def test_build_image_adapter_can_route_xiaole_family_from_capability():
    model_params = _image_model_root({
        'future-xiaole-model': {
            'api_key': 'test-key',
            'base_url': 'https://api.proxy.example.com',
            'endpoint': '/v1/image/created',
            'model': 'gemini-image',
            'generation_size': '9:16',
            'capability': {
                'prompt_policy': 'identity_first',
                'sub_prompt_identity_lock': True,
                'primary_reference_mode': 'identity_anchor',
                'adapter_family': 'xiaole',
                'reference_input_mode': 'reference_images',
                'generation_size_key': 'aspect_ratio',
            },
        }
    })

    adapter = build_image_adapter(model_params, 'future-xiaole-model')

    assert isinstance(adapter, XiaoleImageAdapter)
    assert adapter._aspect_ratio == '9:16'



def test_build_image_adapter_falls_back_to_generic_adapter_for_unknown_family():
    model_params = _image_model_root({
        'future-generic-model': {
            'api_key': 'test-key',
            'base_url': 'https://api.example.com',
            'model': 'generic-image-model',
            'capability': {
                'prompt_policy': 'identity_first',
                'sub_prompt_identity_lock': True,
                'primary_reference_mode': 'identity_anchor',
                'adapter_family': 'generic',
                'reference_input_mode': 'inline_data',
                'generation_size_key': 'image_size',
            },
        }
    })

    adapter = build_image_adapter(model_params, 'future-generic-model')

    assert isinstance(adapter, ImageModelAdapter)
