from __future__ import annotations

import io
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from loguru import logger

from utils.helpers import ensure_dir

if TYPE_CHECKING:
    from drivers.base_driver import BaseDriver


class ScreenshotCapture:
    """截图采集器：单帧截图 + 滚动长截图"""

    def __init__(self, driver: "BaseDriver", output_dir: str,
                 scroll_distance: int = 800,
                 scroll_pause: float = 1.5,
                 status_bar_height: int = 44,
                 max_scrolls: int = 15):
        self.driver = driver
        self.output_dir = ensure_dir(output_dir)
        self.scroll_distance = scroll_distance
        self.scroll_pause = scroll_pause
        self.status_bar_height = status_bar_height
        self.max_scrolls = max_scrolls

    # ──────────────────────────── single frame ───────────────────────────

    def take(self, filename: str) -> Path:
        """单张截图，保存为 PNG"""
        path = self.output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        png = self.driver.screenshot_png()
        img = Image.open(io.BytesIO(png))
        img.save(path, format="PNG")
        logger.debug(f"截图保存: {path}")
        return path

    def take_image(self) -> Image.Image:
        png = self.driver.screenshot_png()
        return Image.open(io.BytesIO(png)).copy()

    # ──────────────────────────── long screenshot ─────────────────────────

    def take_long(self, filename: str, scroll_count: int | None = None) -> Path:
        """
        滚动多次并拼接成长截图。
        使用像素级重叠检测去掉重复区域，避免拼接错位。
        """
        count = scroll_count or self.max_scrolls
        frames: list[Image.Image] = []

        # 1. 截取初始帧
        frames.append(self.take_image())
        logger.info(f"长截图开始，计划滚动 {count} 次")

        for i in range(count):
            self.driver.scroll_down(self.scroll_distance)
            time.sleep(self.scroll_pause)

            new_frame = self.take_image()

            # 检测是否到达页面底部（连续两帧完全相同则停止）
            if frames and self._images_identical(frames[-1], new_frame):
                logger.info(f"第 {i+1} 次滚动后页面未变化，停止")
                break

            frames.append(new_frame)

        stitched = self._stitch(frames)
        path = self.output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        stitched.save(path, format="PNG")
        logger.info(f"长截图保存: {path}  ({stitched.width}×{stitched.height}px, {len(frames)}帧)")
        return path

    # ──────────────────────────── stitching ─────────────────────────────

    def _stitch(self, frames: list[Image.Image]) -> Image.Image:
        if not frames:
            raise ValueError("无截图帧可拼接")
        if len(frames) == 1:
            return frames[0]

        w = frames[0].width
        strips: list[Image.Image] = [frames[0]]

        for prev, curr in zip(frames, frames[1:]):
            overlap = self._find_overlap(prev, curr)
            strip_top = overlap if overlap is not None else self.status_bar_height
            cropped = curr.crop((0, strip_top, w, curr.height))
            strips.append(cropped)

        total_h = sum(s.height for s in strips)
        canvas = Image.new("RGB", (w, total_h))
        y = 0
        for s in strips:
            canvas.paste(s, (0, y))
            y += s.height
        return canvas

    def _find_overlap(self, prev: Image.Image, curr: Image.Image,
                      search_px: int = 120) -> int | None:
        """
        在 curr 顶部找到与 prev 底部最匹配的位置，返回 curr 中应裁掉的行数。
        限制搜索范围在 [status_bar_height, search_px] 之间。
        """
        w = min(prev.width, curr.width)
        strip_h = min(40, search_px // 3)  # 用于匹配的参考条带高度

        # 取 prev 底部的参考条带
        ref_strip = prev.crop((0, prev.height - strip_h, w, prev.height))

        best_y, best_diff = self.status_bar_height, float("inf")

        for y in range(self.status_bar_height, min(search_px, curr.height - strip_h)):
            candidate = curr.crop((0, y, w, y + strip_h))
            diff = self._pixel_diff(ref_strip, candidate)
            if diff < best_diff:
                best_diff = diff
                best_y = y

        # 差异过大说明匹配失败，回退到默认值
        threshold = strip_h * w * 30  # 平均每像素 30 灰度值差
        if best_diff > threshold:
            return None
        return best_y + strip_h  # 裁掉到参考条带结束的所有行

    @staticmethod
    def _pixel_diff(img_a: Image.Image, img_b: Image.Image) -> float:
        import numpy as np
        a = np.array(img_a.convert("L"), dtype=float)
        b = np.array(img_b.convert("L"), dtype=float)
        if a.shape != b.shape:
            return float("inf")
        return float(np.abs(a - b).sum())

    @staticmethod
    def _images_identical(a: Image.Image, b: Image.Image) -> bool:
        import numpy as np
        arr_a = np.array(a)
        arr_b = np.array(b)
        if arr_a.shape != arr_b.shape:
            return False
        return bool((arr_a == arr_b).all())
