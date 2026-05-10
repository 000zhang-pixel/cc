import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "middleware"))

from adapters.ai_models import XiaoleImageAdapter, build_image_adapter


def _model_params_for_nanobanana_xiaole():
    return {
        "image_model": {
            "max_concurrency": 1,
            "retry_max": 0,
            "retry_base_seconds": 0,
            "providers": {
                "nanobanana-2": {
                    "api_key": "sk-valid-key",
                    "base_url": "https://api.xiaoleai.team",
                    "endpoint": "/v1/image/created",
                    "model": "gemini-3.1-flash-image-preview",
                    "aspect_ratio": "9:16",
                }
            },
        }
    }


def test_build_image_adapter_routes_nanobanana2_to_xiaole_adapter_when_endpoint_configured():
    adapter = build_image_adapter(_model_params_for_nanobanana_xiaole(), "nanobanana-2")

    assert isinstance(adapter, XiaoleImageAdapter)
