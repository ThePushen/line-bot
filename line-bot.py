import threading
from flask import Flask, request, abort

from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
from linebot.models.events import (
    JoinEvent,
    LeaveEvent,
    MemberJoinedEvent,
    MemberLeftEvent
)
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Initialize APIs
messaging_api = Configuration(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# Flask app setup
app = Flask(__name__)

# Admin and verification settings
ADMIN_USER_IDS = ['black14369', 'USER_ID_2']
pt_message = "這是預設的 pt 訊息"  # Default message
pending_members = {}  # Dictionary for pending members
SECRET_CODE = "your_secret_password"  # Secret password

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        logging.error(f"Error handling webhook: {e}")
        abort(400)
    return 'OK'

@handler.add(MemberJoinedEvent)
def handle_member_join(event):
    for member in event.joined.members:
        user_id = member.user_id
        pending_members[user_id] = {"verified": False}

        # Send welcome message with secret code
        messaging_api.push_message(
            user_id,
            messages=[
                TextMessageContent(
                    text=f"歡迎加入！請在 300 秒內輸入暗號，否則將被移出群組。\n暗號格式：{SECRET_CODE}"
                )
            ]
        )
        # Start timer for removal
        timer = threading.Timer(300, kick_member_if_unverified, args=(event.source.group_id, user_id))
        pending_members[user_id]["timer"] = timer
        timer.start()

@handler.add(MessageEvent)
def handle_message(event):
    global pt_message
    user_id = event.source.user_id
    message_text = event.message.text.strip()

    try:
        if user_id in pending_members:
            if message_text == SECRET_CODE:
                pending_members[user_id]["verified"] = True
                pending_members[user_id]["timer"].cancel()
                messaging_api.reply_message(
                    reply_token=event.reply_token,
                    messages=[TextMessageContent(text="驗證成功！歡迎加入群組 🎉")]
                )
                del pending_members[user_id]
            else:
                messaging_api.reply_message(
                    reply_token=event.reply_token,
                    messages=[TextMessageContent(text="暗號錯誤，請重新輸入正確的暗號。")]
                )
            return

        # Admin commands
        if message_text.startswith("/pt"):
            if user_id in ADMIN_USER_IDS:
                new_message = message_text[4:].strip()
                if new_message:
                    pt_message = new_message
                    messaging_api.reply_message(
                        reply_token=event.reply_token,
                        messages=[TextMessageContent(text=f"已更新/pt的設置內容：{pt_message}")]
                    )
                else:
                    messaging_api.reply_message(
                        reply_token=event.reply_token,
                        messages=[TextMessageContent(text="請提供更新的訊息內容！")]
                    )
            else:
                messaging_api.reply_message(
                    reply_token=event.reply_token,
                    messages=[TextMessageContent(text="您沒有權限設置/pt消息！")]
                )
        elif message_text == "pt":
            messaging_api.reply_message(
                reply_token=event.reply_token,
                messages=[TextMessageContent(text=f"當前設置的/pt消息是：{pt_message}")]
            )

        # Other commands...
    except Exception as e:
        logging.error(f"Error handling message: {e}")
        messaging_api.reply_message(
            reply_token=event.reply_token,
            messages=[TextMessageContent(text="系統發生錯誤，請稍後再試。")]
        )

def kick_member_if_unverified(group_id, user_id):
    if user_id in pending_members and not pending_members[user_id]["verified"]:
        messaging_api.push_message(
            group_id,
            messages=[TextMessageContent(text=f"用戶 <@{user_id}> 未通過驗證，建議移出群組。")]
        )
        del pending_members[user_id]

if __name__ == "__main__":
    app.run(port=8000)
