from __future__ import annotations

import io
from pathlib import Path
from typing import Union

from loguru import logger

try:
    import easyocr
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    logger.warning("easyocr 未安装，OCR 功能不可用。运行: pip install easyocr")


class OCREngine:
    """EasyOCR 封装，支持中英文混合识别"""

    def __init__(self, languages: list[str] | None = None, gpu: bool = False):
        self._reader = None
        self._languages = languages or ["ch_sim", "en"]
        self._gpu = gpu

    def _init_reader(self) -> None:
        if self._reader is None:
            if not _OCR_AVAILABLE:
                raise RuntimeError("easyocr 未安装")
            logger.info("初始化 OCR 引擎（首次加载较慢）...")
            self._reader = easyocr.Reader(self._languages, gpu=self._gpu)

    def read_image(self, image_input: Union[str, Path, bytes],
                   confidence: float = 0.5) -> list[dict]:
        """
        返回格式: [{"text": str, "confidence": float, "bbox": list}, ...]
        """
        self._init_reader()
        if isinstance(image_input, (str, Path)):
            source = str(image_input)
        else:
            source = image_input  # bytes

        results = self._reader.readtext(source)
        items = []
        for bbox, text, conf in results:
            if conf >= confidence and text.strip():
                items.append({"text": text.strip(), "confidence": round(conf, 3), "bbox": bbox})
        return items

    def read_text(self, image_input: Union[str, Path, bytes],
                  confidence: float = 0.5) -> str:
        """返回纯文本（按 bbox y 坐标从上到下排列）"""
        items = self.read_image(image_input, confidence)
        # 按行 y 坐标排序
        items.sort(key=lambda x: (x["bbox"][0][1] + x["bbox"][2][1]) / 2)
        return "\n".join(i["text"] for i in items)

    def read_region(self, image_bytes: bytes, x: int, y: int,
                    w: int, h: int, confidence: float = 0.5) -> str:
        """只识别截图的指定区域"""
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        region = img.crop((x, y, x + w, y + h))
        buf = io.BytesIO()
        region.save(buf, format="PNG")
        return self.read_text(buf.getvalue(), confidence)
