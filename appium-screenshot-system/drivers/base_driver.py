from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)
from loguru import logger


class BaseDriver(ABC):
    def __init__(self, server_url: str, capabilities: dict, timeout: int = 60):
        self.server_url = server_url
        self.capabilities = capabilities
        self.timeout = timeout
        self.driver: Optional[webdriver.Remote] = None

    # ──────────────────────────── connection ────────────────────────────

    def connect(self) -> None:
        logger.info(f"连接 Appium: {self.server_url}")
        self.driver = webdriver.Remote(
            command_executor=self.server_url,
            desired_capabilities=self.capabilities,
        )
        self.driver.implicitly_wait(10)
        logger.info("Appium 连接成功")

    def disconnect(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            logger.info("Appium 会话已关闭")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    # ──────────────────────────── element helpers ────────────────────────

    def _by_map(self, by: str) -> str:
        mapping = {
            "accessibility id": AppiumBy.ACCESSIBILITY_ID,
            "xpath": AppiumBy.XPATH,
            "class name": AppiumBy.CLASS_NAME,
            "id": AppiumBy.ID,
            "name": AppiumBy.NAME,
            "predicate string": AppiumBy.IOS_PREDICATE,
            "class chain": AppiumBy.IOS_CLASS_CHAIN,
        }
        return mapping.get(by.lower(), by)

    def find(self, by: str, value: str, parent=None, timeout: int = 10):
        source = parent or self.driver
        wait = WebDriverWait(source, timeout)
        return wait.until(EC.presence_of_element_located((self._by_map(by), value)))

    def find_all(self, by: str, value: str, parent=None, timeout: int = 10) -> list:
        source = parent or self.driver
        wait = WebDriverWait(source, timeout)
        try:
            wait.until(EC.presence_of_element_located((self._by_map(by), value)))
        except TimeoutException:
            return []
        return source.find_elements(self._by_map(by), value)

    def try_find(self, by: str, value: str, parent=None) -> Optional[object]:
        try:
            return self.find(by, value, parent=parent, timeout=5)
        except (TimeoutException, NoSuchElementException, WebDriverException):
            return None

    def tap(self, by: str, value: str, parent=None, timeout: int = 10) -> None:
        el = self.find(by, value, parent=parent, timeout=timeout)
        el.click()

    def type_text(self, by: str, value: str, text: str, parent=None) -> None:
        el = self.find(by, value, parent=parent)
        el.clear()
        el.send_keys(text)

    def get_text(self, by: str, value: str, parent=None, default: str = "") -> str:
        el = self.try_find(by, value, parent=parent)
        if el is None:
            return default
        try:
            return el.text or el.get_attribute("label") or el.get_attribute("value") or default
        except Exception:
            return default

    # ──────────────────────────── screenshot ────────────────────────────

    def screenshot_png(self) -> bytes:
        return self.driver.get_screenshot_as_png()

    # ──────────────────────────── scroll ────────────────────────────────

    @abstractmethod
    def scroll_down(self, distance: int = 800) -> None:
        ...

    @abstractmethod
    def scroll_up(self, distance: int = 800) -> None:
        ...

    # ──────────────────────────── misc ──────────────────────────────────

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def current_activity(self) -> str:
        try:
            return self.driver.current_activity or ""
        except Exception:
            return ""

    def hide_keyboard(self) -> None:
        try:
            self.driver.hide_keyboard()
        except Exception:
            pass

    def background_app(self, seconds: int = 2) -> None:
        try:
            self.driver.background_app(seconds)
        except Exception:
            pass
