import discord
from discord.ext import commands
import os
import random
from flask import Flask
from threading import Thread
import google.generativeai as genai
import asyncio
import traceback

# --- 設定 ---
TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = "1016316997086216222"
ALLOWED_CHANNEL_ID = 1374589955996778577  # 許可されたチャンネルID
GREETING_CHANNEL_ID = 1370406946812854404  # あいさつチャンネルID

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-1.5-flash")

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    Thread(target=run).start()

# --- Bot初期化 ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True  # メンバー情報取得に必要
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# --- モード・クイズ設定 ---
MODES = {
    "default": "毒舌AIモード",
    "neet": "ニートモード（自虐）",
    "debate": "論破モード",
    "roast": "超絶煽りモード",
    "tgif": "神崇拝モード（感謝）"
}
current_mode = "default"
active_quizzes = {}

QUIZ_DATA = {
    "アニメ": {
        "簡単": [
            {"question": "『ドラゴンボール』の主人公は誰？", "answer": "孫悟空"},
            {"question": "『ポケモン』のピカチュウの進化前の姿は？", "answer": "ピチュー"}
        ]
    },
    "数学": {
        "簡単": [
            {"question": "1+1は？", "answer": "2"},
            {"question": "3×3は？", "answer": "9"}
        ]
    }
}

# 会話履歴保持(ユーザーID毎にリストで履歴保存)
conversation_histories = {}

# --- 起動時 ---
@bot.event
async def on_ready():
    await tree.sync()
    print(f"ログイン成功: {bot.user}")

# --- 新規メンバー参加時の自動あいさつ ---
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(GREETING_CHANNEL_ID)
    if channel:
        await channel.send(f"{member.mention} さん、ようこそ！楽しくやっていきましょう。")

# --- /mode（ご主人様専用） ---
@tree.command(name="mode", description="モードを切り替えます（ご主人様専用）")
async def mode_cmd(interaction: discord.Interaction, mode: str):
    if str(interaction.user.id) != OWNER_ID:
        await interaction.response.send_message("このコマンドはご主人様専用です。", ephemeral=True)
        return

    global current_mode
    if mode in MODES:
        current_mode = mode
        await interaction.response.send_message(f"モードを『{MODES[mode]}』に変更しました。", ephemeral=True)
    else:
        await interaction.response.send_message(f"無効なモードです。使えるモード: {', '.join(MODES.keys())}", ephemeral=True)

# --- /quizコマンド ---
@tree.command(name="quiz", description="クイズを出題します")
async def quiz_cmd(interaction: discord.Interaction, genre: str, difficulty: str):
    genre_data = QUIZ_DATA.get(genre)
    if not genre_data or difficulty not in genre_data:
        await interaction.response.send_message("ジャンルまたは難易度が無効です。", ephemeral=True)
        return

    quiz = random.choice(genre_data[difficulty])
    user_id = str(interaction.user.id)
    active_quizzes[user_id] = {"answer": quiz["answer"], "channel_id": interaction.channel.id}
    await interaction.user.send(f"問題です: {quiz['question']}\n※このDMに答えを返信してください。")
    await interaction.response.send_message("クイズをDMで送信しました。", ephemeral=True)

# --- 天気など代表回答の簡単処理関数 ---
def handle_representative_answer(content: str) -> (bool, str):
    # 日本関連
    if "日本の天気" in content or "日本の気温" in content:
        return True, "日本の代表的な場所として東京の天気をお伝えします。詳細を知りたい場合は場所を教えてください。"
    # フィリピン関連
    if "フィリピンの天気" in content or "フィリピンの気温" in content:
        return True, "フィリピンの代表としてセブの天気をお伝えします。詳細を知りたい場合は場所を教えてください。"
    # その他の国や地域はここに追加可能
    # 例: "アメリカの天気"ならNYなど
    return False, ""

# --- メッセージ応答処理 ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 指定されたチャンネルとDMのみ応答
    if not isinstance(message.channel, discord.DMChannel) and message.channel.id != ALLOWED_CHANNEL_ID:
        return

    user_id = str(message.author.id)

    # DMでのクイズ解答処理
    if isinstance(message.channel, discord.DMChannel) and user_id in active_quizzes:
        quiz = active_quizzes[user_id]
        answer = quiz["answer"]
        channel = bot.get_channel(quiz["channel_id"])
        if channel:
            if message.content.strip().lower() == answer.lower():
                await channel.send(f"{message.author.name} さんの回答：正解です！お見事です🎉")
            else:
                await channel.send(f"{message.author.name} さんの回答：残念、不正解です。正解は「{answer}」でした。")
        del active_quizzes[user_id]
        return

    # 会話履歴保存・質問履歴連携
    if user_id not in conversation_histories:
        conversation_histories[user_id] = []
    conversation_histories[user_id].append({"role": "user", "content": message.content})

    # 代表的回答かどうか判定
    handled, rep_response = handle_representative_answer(message.content)
    if handled:
        await message.channel.send(rep_response)
        # 代表回答後に続けて詳しく聞きたい場合は別途メッセージを受け取る運用に
        return

    # Gemini応答生成用のプロンプトを作成
    if user_id == OWNER_ID:
        prefix = (
            "ご主人様、いつもお疲れ様です。どんな話でも全力でお応えします。なんでも聞いてください。→ "
        )
    else:
        mode = current_mode
        if mode == "tgif":
            prefix = "神よ、感謝と祈りを捧げながらお答えします。→ "
        elif mode == "neet":
            prefix = "こんな私で良ければ答えさせていただきますね。→ "
        elif mode == "debate":
            prefix = "論理的に粉砕して差し上げます。→ "
        elif mode == "roast":
            prefix = "おいおい、それも分からないのかよ。→ "
        else:
            prefix = "またくだらないこと聞いてきたの？仕方ないから答えてあげる。→ "

    prompt = prefix + message.content

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, model.generate_content, prompt)
        text = response.text
        if len(text) > 2000:
            text = text[:1997] + "..."
        await message.channel.send(text)
        # 会話履歴にBot応答も追加
        conversation_histories[user_id].append({"role": "assistant", "content": text})
    except Exception:
        traceback.print_exc()
        await message.channel.send("応答に失敗しました。")

    await bot.process_commands(message)

# --- 実行 ---
keep_alive()
bot.run(TOKEN)
