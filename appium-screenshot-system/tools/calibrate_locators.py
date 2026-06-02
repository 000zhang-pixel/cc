"""
定位器校准工具：连接真机后，打印当前页面所有可见元素的 accessibility id / label / text，
帮助你确认并更新 config/settings.yaml 中的 locators。

用法:
  python tools/calibrate_locators.py --platform ios --app xiaohongshu
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.loader import ConfigLoader
from drivers.ios_driver import IOSDriver
from utils.logger import setup_logger


def dump_page_source(driver: IOSDriver) -> None:
    from appium.webdriver.common.appiumby import AppiumBy
    from rich.table import Table
    from rich.console import Console

    console = Console()
    table = Table(title="当前页面元素（前50个）")
    table.add_column("类型", style="cyan")
    table.add_column("label")
    table.add_column("name")
    table.add_column("value")
    table.add_column("text")

    elements = driver.driver.find_elements(
        AppiumBy.XPATH, "//*[@label!='' or @name!='' or @value!='']"
    )
    for el in elements[:50]:
        try:
            table.add_row(
                el.tag_name or "",
                el.get_attribute("label") or "",
                el.get_attribute("name") or "",
                el.get_attribute("value") or "",
                el.text or "",
            )
        except Exception:
            pass

    console.print(table)
    print("\n[Page Source 已保存到 output/page_source.xml]")
    Path("output").mkdir(exist_ok=True)
    Path("output/page_source.xml").write_text(driver.driver.page_source, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["ios", "windows"], default="ios")
    parser.add_argument("--app", default="xiaohongshu")
    args = parser.parse_args()

    setup_logger()
    config = ConfigLoader()
    bundle_id = config.app_config(args.app).get("bundle_id_ios", "com.xingin.discover")
    caps = config.ios_caps(bundle_id)

    print(f"连接设备，App={args.app}，bundle_id={bundle_id}")
    driver = IOSDriver(config.appium_url(), caps)
    driver.connect()

    try:
        input("请在手机上手动导航到目标页面，然后按 Enter 打印元素树...")
        dump_page_source(driver)
    finally:
        driver.disconnect()


if __name__ == "__main__":
    main()
