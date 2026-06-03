"""
定位器校准工具：连接真机后，打印当前页面所有可见元素的属性，
帮助确认并更新 config/settings.yaml 中的 locators。

用法:
  python tools/calibrate_locators.py --platform android --app xiaohongshu
  python tools/calibrate_locators.py --platform ios --app xiaohongshu
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.loader import ConfigLoader
from utils.logger import setup_logger


def dump_android(driver) -> None:
    from appium.webdriver.common.appiumby import AppiumBy
    from rich.table import Table
    from rich.console import Console

    console = Console()
    table = Table(title="Android 页面元素（前60个）", show_lines=True)
    table.add_column("class", style="cyan", max_width=30)
    table.add_column("text", max_width=25)
    table.add_column("content-desc", max_width=25)
    table.add_column("resource-id", max_width=35)
    table.add_column("clickable")

    elements = driver.driver.find_elements(
        AppiumBy.XPATH,
        '//*[@text!="" or @content-desc!="" or @resource-id!=""]'
    )
    for el in elements[:60]:
        try:
            table.add_row(
                el.tag_name or "",
                (el.get_attribute("text") or "")[:25],
                (el.get_attribute("content-desc") or "")[:25],
                (el.get_attribute("resource-id") or "")[:35],
                el.get_attribute("clickable") or "",
            )
        except Exception:
            pass

    console.print(table)
    console.print("\n[bold]UIAutomator 常用选择器示例:[/]")
    console.print('  按文本:       new UiSelector().text("搜索")')
    console.print('  按描述:       new UiSelector().description("搜索")')
    console.print('  按 id 模式:   new UiSelector().resourceIdMatches(".*search.*")')
    console.print('  按类名:       new UiSelector().className("android.widget.EditText")')

    Path("output").mkdir(exist_ok=True)
    Path("output/page_source.xml").write_text(driver.driver.page_source, encoding="utf-8")
    print("\n[Page Source 已保存到 output/page_source.xml]")


def dump_ios(driver) -> None:
    from appium.webdriver.common.appiumby import AppiumBy
    from rich.table import Table
    from rich.console import Console

    console = Console()
    table = Table(title="iOS 页面元素（前50个）", show_lines=True)
    table.add_column("type", style="cyan", max_width=35)
    table.add_column("label", max_width=25)
    table.add_column("name", max_width=25)
    table.add_column("value", max_width=20)

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
            )
        except Exception:
            pass

    console.print(table)
    Path("output").mkdir(exist_ok=True)
    Path("output/page_source.xml").write_text(driver.driver.page_source, encoding="utf-8")
    print("\n[Page Source 已保存到 output/page_source.xml]")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["android", "ios"], default="android")
    parser.add_argument("--app", default="xiaohongshu")
    args = parser.parse_args()

    setup_logger()
    config = ConfigLoader()

    if args.platform == "android":
        from drivers.android_driver import AndroidDriver
        app_cfg = config.app_config(args.app)
        package = app_cfg.get("package_android", "com.xingin.discover")
        activity = app_cfg.get("activity_android", "")
        caps = config.android_caps(package, activity)
        print(f"连接 Android 设备，App={args.app}，包名={package}")
        print(f"Appium URL: {config.appium_url()}")
        driver = AndroidDriver(config.appium_url(), caps)
        driver.connect()
        try:
            input("请在手机上导航到目标页面（如搜索结果页），然后按 Enter 打印元素树...")
            dump_android(driver)
        finally:
            driver.disconnect()

    else:
        from drivers.ios_driver import IOSDriver
        app_cfg = config.app_config(args.app)
        bundle_id = app_cfg.get("bundle_id_ios", "com.xingin.discover")
        caps = config.ios_caps(bundle_id)
        print(f"连接 iOS 设备，App={args.app}，bundle_id={bundle_id}")
        driver = IOSDriver(config.appium_url(), caps)
        driver.connect()
        try:
            input("请在手机上导航到目标页面，然后按 Enter 打印元素树...")
            dump_ios(driver)
        finally:
            driver.disconnect()


if __name__ == "__main__":
    main()
