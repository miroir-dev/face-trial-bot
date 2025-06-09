import os
import urllib.parse
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    PostbackEvent, QuickReply, QuickReplyButton, PostbackAction, URIAction  # ★ここに URIAction を追加
)

# ───────── 環境変数（Render の Environment に設定） ─────────
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
CHANNEL_TOKEN  = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

line_bot_api = LineBotApi(CHANNEL_TOKEN)
handler      = WebhookHandler(CHANNEL_SECRET)
app          = Flask(__name__)

# ───────── ヘルスチェック ─────────
@app.route("/", methods=["GET"])
def health():
    return "OK", 200

# ───────── Webhook 入口 ─────────
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# ───────── セッション保持（超簡易） ─────────
STATE = {}  # {user_id: {"face":…, "line":…}}

# ───────── 返信ヘルパ ─────────
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
            "気になる方は下のボタンからどうぞ👇"
        ),
        quick_reply=QuickReply(items=[
            # ★ Discovery 申込（フォームURL直リンク）
            QuickReplyButton(
                action=URIAction(
                    label="Discovery を申し込む",
                    uri="https://form.run/@miroirtokyo?plan=discovery"
                )
            ),
            # ★ メニュー案内（既存のmain_menuへ）
            QuickReplyButton(
                action=PostbackAction(
                    label="他メニューを見る",
                    data="action=main_menu"
                )
            )
        ])
    )

# ───────── メッセージイベント ─────────
@handler.add(MessageEvent, message=TextMessage)
def on_message(event):
    text = event.message.text.strip()
    uid  = event.source.user_id

    if text == "お試し診断":
        STATE[uid] = {}
        line_bot_api.reply_message(event.reply_token, make_q1())

# ───────── Postback イベント ─────────
@handler.add(PostbackEvent)
def on_postback(event):
    data = dict(urllib.parse.parse_qsl(event.postback.data))
    uid  = event.source.user_id
    STATE.setdefault(uid, {})

    # 1) メニュー案内
    if data.get("action") == "main_menu":
        reply_text(
            event.reply_token,
        "【メニュー一覧】\n"
        "———————————\n"
        "🪞 Discovery　￥16,500\n"
        "　似合う軸をAI + プロで特定\n\n"
        "🎨 Design　　￥39,600\n"
        "　服・髪・メイクをトータル提案\n\n"
        "👗 Concierge　￥165,000\n"
        "　45日伴走でイメージ戦略\n\n"
        "お申し込みは『◯◯（メニュー名）』と送るか\n"
        "フォーム▶︎ https://form.run/@miroirtokyo\n"
    )
        return

    # 2) 質問回答処理
    if "face" in data:
        STATE[uid]["face"] = data["face"]
        line_bot_api.reply_message(event.reply_token, make_q2())
        return

    if "line" in data:
        STATE[uid]["line"] = data["line"]
        face = STATE[uid].get("face", "unknown")
        line = STATE[uid].get("line", "unknown")
        line_bot_api.reply_message(event.reply_token, make_result(face, line))
        STATE.pop(uid, None)
        return

# ───────── 起動 ─────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
