import base64
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "middleware"))

from adapters.ai_models import OpenAIImageAdapter


class _FakeResponses:
    def __init__(self):
        self.last_kwargs = None
        self.calls = 0
        self.fail_first = False

    class _StreamCtx:
        def __init__(self, outer, kwargs):
            self.outer = outer
            self.kwargs = kwargs

        def __enter__(self):
            self.outer.calls += 1
            self.outer.last_kwargs = self.kwargs
            if self.outer.fail_first and self.outer.calls == 1:
                raise RuntimeError("multimodal upstream timeout")
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
        raise AssertionError("images.generate should not be called when image_model is configured")


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponses()
        self.images = _FakeImages()


def test_openai_image_adapter_sends_input_image_when_ref_images_present():
    cfg = {
        "api_key": "test-key",
        "base_url": "https://api.example.com/v1",
        "model": "gpt-5.5",
        "image_model": "gpt-image-2",
        "size": "1024x1536",
    }
    shared_cfg = {"max_concurrency": 1, "retry_max": 0, "retry_base_seconds": 0}
    adapter = OpenAIImageAdapter(cfg, shared_cfg)
    adapter._client = _FakeClient()

    result = adapter.generate("keep product identity", ref_images=[b"\x89PNG\r\n\x1a\nabc"])

    assert result == b"fake-image"
    payload = adapter._client.responses.last_kwargs["input"][0]["content"]
    assert payload[0] == {"type": "input_text", "text": "keep product identity"}
    assert payload[1]["type"] == "input_image"
    assert payload[1]["image_url"].startswith("data:image/png;base64,")


def test_openai_image_adapter_falls_back_to_text_only_when_multimodal_reference_call_fails():
    cfg = {
        "api_key": "test-key",
        "base_url": "https://api.example.com/v1",
        "model": "gpt-5.5",
        "image_model": "gpt-image-2",
        "size": "1024x1536",
    }
    shared_cfg = {"max_concurrency": 1, "retry_max": 0, "retry_base_seconds": 0}
    adapter = OpenAIImageAdapter(cfg, shared_cfg)
    adapter._client = _FakeClient()
    adapter._client.responses.fail_first = True

    result = adapter.generate("keep product identity", ref_images=[b"\x89PNG\r\n\x1a\nabc"])

    assert result == b"fake-image"
    assert adapter._client.responses.calls == 2
    payload = adapter._client.responses.last_kwargs["input"][0]["content"]
    assert payload == [{"type": "input_text", "text": "keep product identity"}]
