import base64
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "middleware"))

import adapters.ai_models as ai_models
from adapters.ai_models import ImageModelAdapter, OpenAIImageAdapter, XiaoleImageAdapter, build_image_adapter


class _FakeHttpxResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"downloaded-image"
        self.text = str(payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHttpxClient:
    def __init__(self, post_payload):
        self.post_payload = post_payload
        self.post_calls = []
        self.get_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):
        self.post_calls.append({"url": url, "headers": headers, "json": json})
        return _FakeHttpxResponse(self.post_payload)

    def get(self, url, timeout=None):
        self.get_calls.append({"url": url, "timeout": timeout})
        return _FakeHttpxResponse({})


class _FakeHttpxFactory:
    def __init__(self, post_payload):
        self.post_payload = post_payload
        self.instances = []

    def __call__(self, *args, **kwargs):
        client = _FakeHttpxClient(self.post_payload)
        self.instances.append(client)
        return client


class _FakeResponses:
    def __init__(self):
        self.last_kwargs = None

    class _StreamCtx:
        def __init__(self, outer, kwargs):
            self.outer = outer
            self.kwargs = kwargs

        def __enter__(self):
            self.outer.last_kwargs = self.kwargs
            event = SimpleNamespace(
                type="response.output_item.done",
                item=SimpleNamespace(
                    type="image_generation_call",
                    result=base64.b64encode(b"fake-image").decode("utf-8"),
                ),
            )
            self._events = [event]
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __iter__(self):
            return iter(self._events)

    def stream(self, **kwargs):
        return self._StreamCtx(self, kwargs)


class _FakeImages:
    def generate(self, **kwargs):
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"fake-image").decode("utf-8"), url=None)])


class _FakeOpenAIClient:
    def __init__(self):
        self.responses = _FakeResponses()
        self.images = _FakeImages()



def _image_model_root(providers: dict) -> dict:
    return {
        "image_model": {
            "max_concurrency": 2,
            "retry_max": 0,
            "retry_base_seconds": 0,
            "providers": providers,
        }
    }



def test_openai_runtime_contract_ignores_ref_images_when_capability_disables_input_image():
    model_params = _image_model_root({
        "future-openai-model": {
            "api_key": "test-key",
            "base_url": "https://api.example.com/v1",
            "model": "gpt-5.5",
            "image_model": "gpt-image-2",
            "generation_size": "1024x1536",
            "capability": {
                "prompt_policy": "reference_first",
                "sub_prompt_identity_lock": False,
                "primary_reference_mode": "reference_image",
                "adapter_family": "openai",
                "reference_input_mode": "none",
                "generation_size_key": "size",
            },
        }
    })
    adapter = build_image_adapter(model_params, "future-openai-model")
    adapter._client = _FakeOpenAIClient()

    result = adapter.generate("keep product identity", ref_images=[b"\x89PNG\r\n\x1a\nabc"])

    assert result == b"fake-image"
    payload = adapter._client.responses.last_kwargs["input"][0]["content"]
    assert payload == [{"type": "input_text", "text": "keep product identity"}]



def test_xiaole_runtime_contract_ignores_ref_images_when_capability_disables_reference_images(monkeypatch):
    httpx_factory = _FakeHttpxFactory({"data": [{"b64_json": base64.b64encode(b"fake-image").decode("utf-8")}]})
    monkeypatch.setattr(ai_models.httpx, "Client", httpx_factory)
    model_params = _image_model_root({
        "future-xiaole-model": {
            "api_key": "test-key",
            "base_url": "https://api.proxy.example.com",
            "endpoint": "/v1/image/created",
            "model": "gemini-image",
            "generation_size": "9:16",
            "capability": {
                "prompt_policy": "identity_first",
                "sub_prompt_identity_lock": True,
                "primary_reference_mode": "identity_anchor",
                "adapter_family": "xiaole",
                "reference_input_mode": "none",
                "generation_size_key": "aspect_ratio",
            },
        }
    })
    adapter = build_image_adapter(model_params, "future-xiaole-model")

    result = adapter.generate("prompt", ref_images=[b"\x89PNG\r\n\x1a\nabc"])

    assert result == b"fake-image"
    request_json = httpx_factory.instances[0].post_calls[0]["json"]
    assert request_json["aspect_ratio"] == "9:16"
    assert "reference_images" not in request_json



def test_generic_runtime_contract_maps_generation_size_to_image_size_and_keeps_inline_data(monkeypatch):
    httpx_factory = _FakeHttpxFactory({
        "candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(b"fake-image").decode("utf-8")}}]}}]
    })
    monkeypatch.setattr(ai_models.httpx, "Client", httpx_factory)
    model_params = _image_model_root({
        "future-generic-model": {
            "api_key": "test-key",
            "base_url": "https://api.example.com",
            "model": "generic-image-model",
            "generation_size": "2K",
            "capability": {
                "prompt_policy": "identity_first",
                "sub_prompt_identity_lock": True,
                "primary_reference_mode": "identity_anchor",
                "adapter_family": "generic",
                "reference_input_mode": "inline_data",
                "generation_size_key": "image_size",
            },
        }
    })
    adapter = build_image_adapter(model_params, "future-generic-model")

    result = adapter.generate("prompt", ref_images=[b"\x89PNG\r\n\x1a\nabc"])

    assert result == b"fake-image"
    request_json = httpx_factory.instances[0].post_calls[0]["json"]
    assert request_json["generationConfig"]["imageConfig"]["imageSize"] == "2K"
    parts = request_json["contents"][0]["parts"]
    assert parts[0]["inlineData"]["mimeType"] == "image/png"
    assert parts[-1] == {"text": "prompt"}
