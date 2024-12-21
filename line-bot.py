import threading
from flask import Flask, request, abort
from linebot import LineBotApi
from linebot.v3.webhook import WebhookHandler
from linebot.models import (MessageEvent, TextMessage, TextSendMessage, MemberJoinedEvent)
import os
from dotenv import load_dotenv
import logging

# 載入環境變數
load_dotenv()
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

app = Flask(__name__)

# 設定管理員的 User ID 列表
ADMIN_USER_IDS = ['black14369', 'USER_ID_2']
pt_message = "這是預設的 pt 訊息"  # 默認的 pt 訊息
pending_members = {}  # 用來儲存待驗證成員的字典
SECRET_CODE = "your_secret_password"  # 你的暗號設定

# Webhook 處理
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        abort(400)
    return 'OK'

# 偵測新成員加入事件
@handler.add(MemberJoinedEvent)
def handle_member_join(event):
    for member in event.joined.members:
        user_id = member.user_id
        pending_members[user_id] = {"verified": False}

        # 發送歡迎訊息與暗號驗證
        line_bot_api.push_message(
            user_id,
            TextSendMessage(
                text=f"歡迎加入！請在 300 秒內輸入暗號，否則將被移出群組。\n暗號格式：{SECRET_CODE}"
            )
        )
        # 啟動倒計時檢查
        timer = threading.Timer(300, kick_member_if_unverified, args=(event.source.group_id, user_id))
        pending_members[user_id]["timer"] = timer
        timer.start()

# 處理消息事件
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global pt_message
    user_id = event.source.user_id
    message_text = event.message.text.strip()

    try:
        # 驗證新成員
        if user_id in pending_members:
            if message_text == SECRET_CODE:
                pending_members[user_id]["verified"] = True
                pending_members[user_id]["timer"].cancel()
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="驗證成功！歡迎加入群組 🎉")
                )
                del pending_members[user_id]
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="暗號錯誤，請重新輸入正確的暗號。")
                )
            return

        # 檢查是否是管理員發送指令
        if message_text.startswith("/pt"):
            if user_id in ADMIN_USER_IDS:
                # 提取/pt後的設置內容
                new_message = message_text[4:].strip()  # 去掉 "/pt " 前綴
                if new_message:
                    pt_message = new_message  # 更新 pt 訊息內容
                    line_bot_api.reply_message(
                        event.reply_token, 
                        TextSendMessage(text=f"已更新/pt的設置內容：{pt_message}")
                    )
                else:
                    line_bot_api.reply_message(
                        event.reply_token, 
                        TextSendMessage(text="請提供更新的訊息內容！")
                    )
            else:
                line_bot_api.reply_message(
                    event.reply_token, 
                    TextSendMessage(text="您沒有權限設置/pt消息！")
                )
        elif message_text == "pt":
            # 普通用戶查詢/pt的內容
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text=f"當前設置的/pt消息是：{pt_message}")
            )
        # 其他指令處理...
        elif message_text.startswith("/add_admin"):
            if user_id in ADMIN_USER_IDS:
                user_to_add = message_text[len("/add_admin "):].strip()
                if user_to_add:
                    ADMIN_USER_IDS.append(user_to_add)
                    response = f"已將用戶 {user_to_add} 添加為管理員。"
                else:
                    response = "請提供要添加的用戶 ID。"
            else:
                response = "您沒有權限執行此操作。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response))

        elif message_text.startswith("/remove_admin"):
            if user_id in ADMIN_USER_IDS:
                user_to_remove = message_text[len("/remove_admin "):].strip()
                if user_to_remove in ADMIN_USER_IDS:
                    ADMIN_USER_IDS.remove(user_to_remove)
                    response = f"已將用戶 {user_to_remove} 移除為管理員。"
                else:
                    response = f"用戶 {user_to_remove} 不是管理員。"
            else:
                response = "您沒有權限執行此操作。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response))

        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="無效指令，請輸入正確的管理員指令。")
            )

    except Exception as e:
        logging.error(f"處理訊息時出現錯誤: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="系統發生錯誤，請稍後再試。")
        )

# 未通過驗證則踢出用戶
def kick_member_if_unverified(group_id, user_id):
    if user_id in pending_members and not pending_members[user_id]["verified"]:
        # 通知管理員
        line_bot_api.push_message(
            group_id,
            TextSendMessage(
                text=f"用戶 <@{user_id}> 未通過驗證，建議移出群組。"
            )
        )
        del pending_members[user_id]

if __name__ == "__main__":
    app.run(port=8000)
