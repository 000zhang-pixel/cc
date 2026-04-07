"""
AI model adapters — unified interface over text / image / video providers.

Text models (GPT-4.1, Kimi K2.5, DeepSeek) all expose OpenAI-compatible
chat completions, so they share one adapter base class.

Image and video models use provider-specific httpx calls.
"""
import asyncio
import base64
import logging
import threading
import time
from abc import ABC, abstractmethod

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _with_retry(fn, max_retries: int, base_seconds: float):
    """Synchronous exponential-backoff retry wrapper."""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt == max_retries:
                break
            wait = base_seconds * (3 ** attempt)
            logger.warning(
                "Attempt %d/%d failed (%s). Retrying in %.0fs…",
                attempt + 1, max_retries + 1, exc, wait,
            )
            time.sleep(wait)
    raise last_exc


# ---------------------------------------------------------------------------
# Semaphore registry (one per model class, shared across all instances)
# ---------------------------------------------------------------------------

_semaphores: dict[str, threading.Semaphore] = {}


def _get_semaphore(key: str, max_concurrency: int) -> threading.Semaphore:
    if key not in _semaphores:
        _semaphores[key] = threading.Semaphore(max_concurrency)
    return _semaphores[key]


# ---------------------------------------------------------------------------
# Text model adapter (OpenAI-compatible)
# ---------------------------------------------------------------------------

class TextModelAdapter:
    """
    Wraps any OpenAI-compatible text API.
    Provider name is used as the semaphore key shared across all instances
    of the same provider within this process.
    """

    def __init__(self, provider: str, cfg: dict, shared_cfg: dict):
        """
        provider: e.g. "gpt-4.1"
        cfg: provider sub-dict from model_params.yaml
        shared_cfg: top-level text_model dict (max_concurrency, retry_*)
        """
        self._provider = cfg.get("model", provider)  # yaml model字段优先，否则用provider名
        self._client = OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg.get("base_url", "https://api.openai.com/v1"),
        )
        self._max_tokens = cfg.get("max_tokens", 4096)
        self._semaphore = _get_semaphore("text", shared_cfg["max_concurrency"])
        self._retry_max = shared_cfg["retry_max"]
        self._retry_base = shared_cfg["retry_base_seconds"]

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the assistant message text."""
        def _call():
            with self._semaphore:
                resp = self._client.chat.completions.create(
                    model=self._provider,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=self._max_tokens,
                )
                return resp.choices[0].message.content or ""

        return _with_retry(_call, self._retry_max, self._retry_base)


# ---------------------------------------------------------------------------
# Image model adapter (Nanobanana 2 — provider-specific REST API)
# ---------------------------------------------------------------------------

class ImageModelAdapter:
    """
    Calls Nanobanana 2 image generation API (runapi.co — Gemini-style endpoint).

    Request format:
        POST /v1beta/models/{model}:generateContent?key=
        Authorization: Bearer <token>
        {
          "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": "<base64>"}},  # optional ref image
            {"text": "<prompt>"}
          ]}],
          "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": "9:16", "imageSize": "1K"}
          }
        }

    Response: parts may contain inlineData (base64 image) or text.
    Returns raw image bytes.
    """

    def __init__(self, cfg: dict, shared_cfg: dict):
        self._api_key  = cfg["api_key"]
        self._base_url = cfg.get("base_url", "https://runapi.co").rstrip("/")
        self._model    = cfg.get("model", "gemini-3.1-flash-image-preview")
        self._aspect_ratio = cfg.get("aspect_ratio", "9:16")
        self._image_size   = cfg.get("image_size", "1K")
        self._semaphore = _get_semaphore("image", shared_cfg["max_concurrency"])
        self._retry_max = shared_cfg["retry_max"]
        self._retry_base = shared_cfg["retry_base_seconds"]

    @staticmethod
    def _detect_mime(data: bytes) -> str:
        """Detect image MIME type from magic bytes."""
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"  # fallback

    def generate(self, prompt: str, ref_images: list[bytes] | None = None) -> bytes:
        """Generate an image from prompt. Returns raw image bytes (JPEG/PNG).

        ref_images: optional list of reference images (e.g. 白底图) passed as inlineData
                    before the text prompt. Each is a raw bytes object.
        """
        url = f"{self._base_url}/v1/models/{self._model}:generateContent"
        parts = []
        for img_bytes in (ref_images or []):
            mime = self._detect_mime(img_bytes)
            parts.append({
                "inlineData": {
                    "mimeType": mime,
                    "data": base64.b64encode(img_bytes).decode("utf-8"),
                }
            })
        parts.append({"text": prompt})

        payload = {
            "contents": [
                {"role": "user", "parts": parts}
            ],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {
                    "aspectRatio": self._aspect_ratio,
                    "imageSize": self._image_size,
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        def _call():
            with self._semaphore:
                with httpx.Client(timeout=180) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    # Extract image from response — supports inlineData (base64) and fileData (URL)
                    candidates = data.get("candidates") or []
                    for candidate in candidates:
                        parts_resp = (candidate.get("content") or {}).get("parts") or []
                        for part in parts_resp:
                            inline = part.get("inlineData")
                            if inline:
                                return base64.b64decode(inline["data"])
                            file_data = part.get("fileData")
                            if file_data and file_data.get("fileUri"):
                                dl = client.get(file_data["fileUri"], timeout=60)
                                dl.raise_for_status()
                                return dl.content
                    raise RuntimeError(f"Nanobanana: no image data in response: {data}")

        return _with_retry(_call, self._retry_max, self._retry_base)

    def generate_sequential(
        self,
        master_prompt: str,
        sub_prompts: list[str],
        ref_images: list[bytes] | None = None,
    ) -> list[bytes]:
        """
        Generate N images independently.
        master_prompt: overall context / consistency instructions
        sub_prompts: per-image specific prompts
        ref_images: reference images (e.g. 白底图) passed to every call for product/style consistency
        """
        results = []
        for sub in sub_prompts:
            combined = f"{master_prompt}\n\n---\n\n{sub}"
            results.append(self.generate(combined, ref_images=ref_images))
        return results

class VolcEngineImageAdapter:
    """
    Calls Volcano Engine ARK image generation API (doubao-seedream series).
    Uses the OpenAI-compatible images.generate endpoint.
    Returns raw image bytes.
    """

    def __init__(self, cfg: dict, shared_cfg: dict):
        self._client = OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
        )
        self._model = cfg["model"]
        self._size = cfg.get("size", "1024x1024")
        self._semaphore = _get_semaphore("image", shared_cfg["max_concurrency"])
        self._retry_max = shared_cfg["retry_max"]
        self._retry_base = shared_cfg["retry_base_seconds"]

    def generate(self, prompt: str) -> bytes:
        """Generate an image from prompt. Returns raw image bytes (JPEG/PNG)."""
        def _call():
            with self._semaphore:
                resp = self._client.images.generate(
                    model=self._model,
                    prompt=prompt,
                    size=self._size,
                    n=1,
                )
                item = resp.data[0]
                if item.url:
                    with httpx.Client(timeout=120) as client:
                        r = client.get(item.url)
                        r.raise_for_status()
                        return r.content
                if item.b64_json:
                    return base64.b64decode(item.b64_json)
                raise RuntimeError("VolcEngine: no image data in response")

        return _with_retry(_call, self._retry_max, self._retry_base)


# ---------------------------------------------------------------------------
# Video model adapter (Volcano Engine — ARK async task API)
# ---------------------------------------------------------------------------

class VolcEngineVideoAdapter:
    """
    Calls Volcano Engine ARK video generation API (doubao-seedance series).
    Async flow: POST to create task → GET to poll → download MP4.
    Returns raw video bytes.
    """
    _TASK_URL = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"

    def __init__(self, cfg: dict, shared_cfg: dict):
        self._api_key = cfg["api_key"]
        self._model = cfg["model"]
        self._resolution = cfg.get("resolution", "720p")
        self._ratio = cfg.get("ratio", "16:9")
        self._semaphore = _get_semaphore("video", shared_cfg["max_concurrency"])
        self._retry_max = shared_cfg["retry_max"]
        self._retry_base = shared_cfg["retry_base_seconds"]

    def generate(self, prompt: str, min_seconds: int = 5, max_seconds: int = 12) -> bytes:
        """Submit task, poll until succeeded, download and return video bytes."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        duration = min(max(min_seconds, 5), 12)  # ARK supports 2–12s; clamp safely

        def _call():
            with self._semaphore:
                with httpx.Client(timeout=30) as client:
                    # Submit task
                    submit = client.post(
                        self._TASK_URL,
                        headers=headers,
                        json={
                            "model": self._model,
                            "content": [{"type": "text", "text": prompt}],
                            "resolution": self._resolution,
                            "ratio": self._ratio,
                            "duration": duration,
                        },
                    )
                    submit.raise_for_status()
                    task_id = submit.json().get("id")
                    if not task_id:
                        raise RuntimeError(f"VolcEngine video: no task id in response: {submit.text}")

                    logger.info("VolcEngine video task submitted: %s", task_id)

                    # Poll until done (up to 10 min)
                    for _ in range(120):
                        time.sleep(5)
                        poll = client.get(
                            f"{self._TASK_URL}/{task_id}",
                            headers=headers,
                            timeout=20,
                        )
                        poll.raise_for_status()
                        data = poll.json()
                        status = data.get("status", "")
                        if status == "succeeded":
                            video_url = (data.get("content") or {}).get("video_url")
                            if not video_url:
                                raise RuntimeError(f"VolcEngine video: no video_url in response: {data}")
                            with httpx.Client(timeout=300) as dl_client:
                                dl = dl_client.get(video_url)
                                dl.raise_for_status()
                                return dl.content
                        if status == "failed":
                            err = data.get("error") or {}
                            raise RuntimeError(
                                f"VolcEngine video task {task_id} failed: {err.get('code')} — {err.get('message')}"
                            )

                    raise TimeoutError(f"VolcEngine video task {task_id} timed out after 10 minutes")

        return _with_retry(_call, self._retry_max, self._retry_base)


# ---------------------------------------------------------------------------
# Video model adapter (Veo 3 — provider-specific REST API)
# ---------------------------------------------------------------------------

class VideoModelAdapter:
    """
    Calls Veo 3 video generation API.
    Veo 3 is typically async: submit job → poll → download.
    Returns raw video bytes.
    """

    def __init__(self, cfg: dict, shared_cfg: dict):
        self._api_key = cfg["api_key"]
        self._base_url = cfg["base_url"].rstrip("/")
        self._semaphore = _get_semaphore("video", shared_cfg["max_concurrency"])
        self._retry_max = shared_cfg["retry_max"]
        self._retry_base = shared_cfg["retry_base_seconds"]

    def generate(self, prompt: str, min_seconds: int = 15, max_seconds: int = 60) -> bytes:
        """Submit video generation job and block until complete. Returns video bytes."""
        def _call():
            with self._semaphore:
                with httpx.Client(timeout=30) as client:
                    # Submit job
                    submit_resp = client.post(
                        f"{self._base_url}/generate",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json={
                            "prompt": prompt,
                            "min_duration": min_seconds,
                            "max_duration": max_seconds,
                        },
                    )
                    submit_resp.raise_for_status()
                    job_id = submit_resp.json().get("job_id") or submit_resp.json().get("id")
                    if not job_id:
                        raise RuntimeError(f"Veo3: no job_id in response: {submit_resp.text}")

                    # Poll until done (up to 20 min)
                    for _ in range(240):
                        time.sleep(5)
                        status_resp = client.get(
                            f"{self._base_url}/jobs/{job_id}",
                            headers={"Authorization": f"Bearer {self._api_key}"},
                        )
                        status_resp.raise_for_status()
                        status_data = status_resp.json()
                        status = status_data.get("status", "")
                        if status in ("completed", "done", "succeeded"):
                            video_url = status_data.get("url") or status_data.get("video_url")
                            dl = client.get(video_url, timeout=300)
                            dl.raise_for_status()
                            return dl.content
                        if status in ("failed", "error"):
                            raise RuntimeError(f"Veo3 job {job_id} failed: {status_data}")

                    raise TimeoutError(f"Veo3 job {job_id} timed out after 20 minutes")

        return _with_retry(_call, self._retry_max, self._retry_base)


# ---------------------------------------------------------------------------
# Vision model adapter (OpenAI-compatible, supports base64 image in messages)
# ---------------------------------------------------------------------------

class VisionModelAdapter:
    """
    Sends an image (raw bytes) + text prompt to an OpenAI-compatible vision model.
    Returns the assistant's text response.
    """

    def __init__(self, cfg: dict, shared_cfg: dict):
        self._client = OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg.get("base_url", "https://api.openai.com/v1"),
        )
        self._model = cfg["model"]
        self._max_tokens = cfg.get("max_tokens", 1024)
        self._semaphore = _get_semaphore("vision", shared_cfg["max_concurrency"])
        self._retry_max = shared_cfg["retry_max"]
        self._retry_base = shared_cfg["retry_base_seconds"]

    def analyze(self, system: str, user_text: str, image_bytes: bytes) -> str:
        """Send image + text to vision model. Returns assistant text."""
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:image/jpeg;base64,{b64}"

        def _call():
            with self._semaphore:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": image_url}},
                                {"type": "text", "text": user_text},
                            ],
                        },
                    ],
                    max_tokens=self._max_tokens,
                )
                return resp.choices[0].message.content or ""

        return _with_retry(_call, self._retry_max, self._retry_base)


# ---------------------------------------------------------------------------
# Factory — build adapters from config
# ---------------------------------------------------------------------------

def build_text_adapter(provider_name: str, model_params: dict) -> TextModelAdapter:
    """provider_name: value from Feishu 文案模型 field, e.g. 'gpt-4.1'"""
    cfg_root = model_params["text_model"]
    provider_cfg = cfg_root["providers"].get(provider_name)
    if provider_cfg is None:
        raise ValueError(f"Unknown text model provider: {provider_name!r}")
    return TextModelAdapter(provider_name, provider_cfg, cfg_root)


def build_image_adapter(model_params: dict, provider_name: str = None):
    cfg_root = model_params["image_model"]
    providers = cfg_root["providers"]
    if provider_name is None:
        provider_name = next(iter(providers))
    provider_cfg = providers.get(provider_name)
    if provider_cfg is None:
        raise ValueError(f"Unknown image model provider: {provider_name!r}")
    if "volcengine" in provider_name:
        return VolcEngineImageAdapter(provider_cfg, cfg_root)
    return ImageModelAdapter(provider_cfg, cfg_root)


def build_video_adapter(model_params: dict, provider_name: str = None):
    cfg_root = model_params["video_model"]
    providers = cfg_root["providers"]
    if provider_name is None:
        provider_name = next(iter(providers))
    provider_cfg = providers.get(provider_name)
    if provider_cfg is None:
        raise ValueError(f"Unknown video model provider: {provider_name!r}")
    if "model" in provider_cfg:
        return VolcEngineVideoAdapter(provider_cfg, cfg_root)
    return VideoModelAdapter(provider_cfg, cfg_root)


def build_vision_adapter(model_params: dict) -> "VisionModelAdapter | None":
    """Returns VisionModelAdapter for the first configured vision provider, or None if not configured."""
    cfg_root = model_params.get("vision_model")
    if not cfg_root:
        return None
    providers = cfg_root.get("providers", {})
    if not providers:
        return None
    provider_cfg = next(iter(providers.values()))
    # Skip if api_key is still an unexpanded placeholder
    if not provider_cfg.get("api_key") or "${" in str(provider_cfg.get("api_key", "")):
        return None
    return VisionModelAdapter(provider_cfg, cfg_root)
