import threading
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import ApiClient, MessagingApi, ReplyMessageRequest
from linebot.v3.webhooks import MessageEvent, TextMessageContent, MemberJoinedEvent
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Initialize APIs
line_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
line_channel_secret = os.getenv("LINE_CHANNEL_SECRET")
handler = WebhookHandler(line_channel_secret)
api_client = ApiClient(access_token=line_access_token)
messaging_api = MessagingApi(api_client)

# Flask app setup
app = Flask(__name__)

# Admin and verification settings
ADMIN_USER_IDS = ['black14369', 'USER_ID_2']
pt_message = "這是預設的訊息"  # Default message
pending_members = {}  # Dictionary for pending members
SECRET_CODE = "your_secret_password"  # Secret password

# Logging setup
logging.basicConfig(level=logging.INFO)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')

    # Get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # Handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'


@handler.add(MessageEvent)
def handle_message(event):
    user_id = event.source.user_id
    message_text = event.message.text.strip()

    logging.info(f"User ID: {user_id}, Message: {message_text}")

    # Example reply
    if message_text == "ping":
        reply_message = "pong"
    else:
        reply_message = f"Your User ID: {user_id}"

    try:
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessageContent(text=reply_message)]
            )
        )
    except Exception as e:
        logging.error(f"Error replying to message: {e}")


@handler.add(MemberJoinedEvent)
def handle_member_join(event):
    for member in event.joined.members:
        user_id = member.user_id
        pending_members[user_id] = {"verified": False}

        # Send welcome message
        try:
            messaging_api.push_message(
                to=user_id,
                messages=[
                    TextMessageContent(
                        text=f"歡迎加入！請在 300 秒內輸入暗號，否則將被移出群組。\n暗號格式：{SECRET_CODE}"
                    )
                ]
            )
        except Exception as e:
            logging.error(f"Error sending welcome message: {e}")

        # Start timer for removal
        timer = threading.Timer(300, kick_member_if_unverified, args=(event.source.group_id, user_id))
        pending_members[user_id]["timer"] = timer
        timer.start()


def kick_member_if_unverified(group_id, user_id):
    if user_id in pending_members and not pending_members[user_id]["verified"]:
        try:
            messaging_api.push_message(
                to=group_id,
                messages=[TextMessageContent(text=f"用戶 <@{user_id}> 未通過驗證，建議移出群組。")]
            )
            del pending_members[user_id]
        except Exception as e:
            logging.error(f"Error kicking member: {e}")


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
