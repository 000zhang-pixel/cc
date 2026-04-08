"""
飞书群通知功能测试脚本
快速验证 send_group_text 是否正常工作

运行方式：
    cd D:/AI-Content-Hub/middleware
    python test_notify.py
"""
import sys
import os
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(".env")

from adapters.feishu import FeishuClient

def main():
    print("=== 飞书群通知测试 ===")

    # 初始化客户端
    client = FeishuClient(
        app_id=os.environ["LARK_APP_ID"],
        app_secret=os.environ["LARK_APP_SECRET"],
        base_token=os.environ["LARK_BASE_TOKEN"],
    )

    chat_id = "oc_2a18512a232920019a216346de01379a"

    # 测试消息
    test_messages = [
        "📋 待发布+1｜Pub_260408_001_img01｜得物｜等待发布",
        "✅ 发布成功｜Pub_260408_001_img01｜得物｜04-08 15:30",
        "❌ 发布失败｜Pub_260408_002_img01｜原因：本地工作区不存在",
    ]

    for i, msg in enumerate(test_messages, 1):
        print(f"\n[{i}/3] 发送: {msg[:50]}...")
        try:
            client.send_group_text(chat_id, msg)
            print("  ✅ 发送成功")
        except Exception as exc:
            print(f"  ❌ 发送失败: {exc}")

    print("\n=== 测试完成，请检查飞书群消息 ===")

if __name__ == "__main__":
    main()
