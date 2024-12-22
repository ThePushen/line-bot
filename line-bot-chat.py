import threading
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import MessagingApi, TextMessage, ReplyMessageRequest
from linebot.v3.webhooks import MemberJoinedEvent, MessageEvent
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Initialize APIs
messaging_api = MessagingApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# Flask app setup
app = Flask(__name__)

# Admin and verification settings
ADMIN_USER_IDS = []  # Add your USER_ID after obtaining it
pt_message = "這是預設的訊息"
pending_members = {}  # Dictionary for pending members
SECRET_CODE = "your_secret_password"  # Secret password

@app.route("/", methods=['GET'])
def home():
    return "LINE Bot is running!", 200

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature error.")
        abort(400)

    return 'OK'

@handler.add(MemberJoinedEvent)
def handle_member_join(event):
    for member in event.joined.members:
        user_id = member.user_id
        group_id = event.source.group_id
        pending_members[user_id] = {"verified": False}

        try:
            # Send welcome message with secret code
            messaging_api.push_message(
                to=user_id,
                messages=[
                    TextMessage(
                        text=f"歡迎加入！請在 300 秒內輸入暗號，否則將被移出群組。\n暗號格式：{SECRET_CODE}"
                    )
                ]
            )
            # Start timer for removal
            timer = threading.Timer(300, kick_member_if_unverified, args=(group_id, user_id))
            pending_members[user_id]["timer"] = timer
            timer.start()
        except Exception as e:
            app.logger.error(f"Error sending message to {user_id}: {e}")

@handler.add(MessageEvent)
def handle_message(event):
    global pt_message
    user_id = event.source.user_id
    group_id = event.source.group_id
    message_text = event.message.text.strip()

    try:
        if user_id in pending_members:
            if message_text == SECRET_CODE:
                pending_members[user_id]["verified"] = True
                pending_members[user_id]["timer"].cancel()
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="驗證成功！歡迎加入群組 🎉")]
                    )
                )
                del pending_members[user_id]
            else:
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="暗號錯誤，請重新輸入正確的暗號。")]
                    )
                )
            return

        # Handle admin commands
        if message_text.startswith("/pt"):
            if user_id in ADMIN_USER_IDS:
                new_message = message_text[4:].strip()
                if new_message:
                    pt_message = new_message
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=f"已更新/pt的設置內容：{pt_message}")]
                        )
                    )
                else:
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="請提供更新的訊息內容！")]
                        )
                    )
            else:
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="您沒有權限設置/pt消息！")]
                    )
                )
        elif message_text == "pt":
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"當前設置的/pt消息是：{pt_message}")]
                )
            )
        elif message_text.startswith("/add_admin"):
            if user_id in ADMIN_USER_IDS:
                new_admin_id = message_text[11:].strip()
                if new_admin_id and new_admin_id not in ADMIN_USER_IDS:
                    ADMIN_USER_IDS.append(new_admin_id)
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=f"成功新增管理員：{new_admin_id}")]
                        )
                    )
                else:
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="新增失敗，該用戶已是管理員或 ID 無效。")]
                        )
                    )
            else:
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="您沒有權限新增管理員！")]
                    )
                )
        elif message_text == "/my_id":
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"您的 USER_ID 是：{user_id}")]
                )
            )
    except Exception as e:
        logging.error(f"Error handling message: {e}")
        messaging_api.reply_message(
            reply_token=event.reply_token,
            messages=[TextMessage(text="系統發生錯誤，請稍後再試。")]
        )

def kick_member_if_unverified(group_id, user_id):
    if user_id in pending_members and not pending_members[user_id]["verified"]:
        try:
            messaging_api.push_message(
                to=group_id,
                messages=[TextMessage(text=f"用戶 <@{user_id}> 未通過驗證，建議移出群組。")]
            )
            del pending_members[user_id]
        except Exception as e:
            app.logger.error(f"Error kicking user {user_id}: {e}")

if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
