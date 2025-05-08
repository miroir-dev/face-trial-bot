import os
import urllib.parse
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    PostbackEvent, QuickReply, QuickReplyButton, PostbackAction
)

# ────────────────────────────────────────────────
# 環境変数（Render の Environment に設定済みの想定）
# ────────────────────────────────────────────────
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CHANNEL_TOKEN  = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

line_bot_api = LineBotApi(CHANNEL_TOKEN)
handler      = WebhookHandler(CHANNEL_SECRET)
app          = Flask(__name__)

# ────────────────────────────────────────────────
# ヘルスチェック 200 OK
# ────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return "OK", 200

# ────────────────────────────────────────────────
# Webhook 受信
# ────────────────────────────────────────────────
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# ────────────────────────────────────────────────
# セッション保存用（超簡易）
# ────────────────────────────────────────────────
STATE = {}   # {user_id: {"face": str|None, "line": str|None}}

# ────────────────────────────────────────────────
# 返信ヘルパ
# ────────────────────────────────────────────────
def reply_text(token, text):
    line_bot_api.reply_message(token, TextSendMessage(text=text))

def make_q1():
    return TextSendMessage(
        text="【Q1】第一印象はどちらに近い？",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=PostbackAction(label="明るく元気", data="face=child")),
            QuickReplyButton(action=PostbackAction(label="落ち着きがある", data="face=adult")),
            QuickReplyButton(action=PostbackAction(label="分からない", data="face=unknown")),
        ])
    )

def make_q2():
    return TextSendMessage(
        text="【Q2】顔立ちの線の印象は？",
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=PostbackAction(label="丸みが多い", data="line=curve")),
            QuickReplyButton(action=PostbackAction(label="シャープ", data="line=straight")),
            QuickReplyButton(action=PostbackAction(label="分からない", data="line=unknown")),
        ])
    )

def make_result(face, line):
    TYPES = {
        ("child", "straight"): ("クリア",   "すっきり・爽やか"),
        ("child", "curve")   : ("プリティ", "かわいらしい・親しみやすい"),
        ("adult", "curve")   : ("レディ",   "上品・女性らしい"),
        ("adult", "straight"): ("シャープ", "知的・スタイリッシュ"),
        "neutral"            : ("ニュートラル", "バランス型")
    }
    if "unknown" in (face, line):
        t_name, t_kw = TYPES["neutral"]
    else:
        t_name, t_kw = TYPES.get((face, line), TYPES["neutral"])

    return TextSendMessage(
        text=(
            f"🔍 仮診断結果：{t_name} タイプかも！\n"
            f"特徴：{t_kw}\n\n"
            "詳しく知りたい方は下のボタンを押してください👇"
        ),
        quick_reply=QuickReply(items=[
            QuickReplyButton(action=PostbackAction(label="詳しく知りたい？▶︎", data="action=main_menu"))
        ])
    )

# ────────────────────────────────────────────────
# メッセージイベント（「お試し診断」トリガーのみ受ける）
# ────────────────────────────────────────────────
@handler.add(MessageEvent, message=TextMessage)
def on_message(event):
    text = event.message.text.strip()
    uid  = event.source.user_id

    if text == "お試し診断":
        STATE[uid] = {}            # 新規セッション
        line_bot_api.reply_message(event.reply_token, make_q1())

# ────────────────────────────────────────────────
# Postback イベント（質問回答 & メニュー表示）
# ────────────────────────────────────────────────
@handler.add(PostbackEvent)
def on_postback(event):
    data = dict(urllib.parse.parse_qsl(event.postback.data))
    uid  = event.source.user_id
    STATE.setdefault(uid, {})

    # 1) 詳細メニュー案内
    if data.get("action") == "main_menu":
        reply_text(
            event.reply_token,
            "📢 本診断メニュー\n・料金プラン\n・診断の流れ\nご希望の方はこのチャットで「詳細希望」と送ってください😊"
        )
        return

    # 2) Q1/Q2 の回答処理
    if "face" in data:
        STATE[uid]["face"] = data["face"]
        line_bot_api.reply_message(event.reply_token, make_q2())
        return

    if "line" in data:
        STATE[uid]["line"] = data["line"]
        face = STATE[uid].get("face", "unknown")
        line = STATE[uid].get("line", "unknown")
        line_bot_api.reply_message(event.reply_token, make_result(face, line))
        STATE.pop(uid, None)   # セッション終了
        return

# ────────────────────────────────────────────────
# 起動
# ────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
