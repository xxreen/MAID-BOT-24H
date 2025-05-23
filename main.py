import discord
from discord.ext import commands
import os
import random
from flask import Flask
from threading import Thread
import google.generativeai as genai
import asyncio
import traceback
import datetime

# --- 設定 ---
TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = "1016316997086216222"
ALLOWED_CHANNEL_ID = 1374589955996778577
WELCOME_CHANNEL_ID = 1370406946812854404

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
intents.members = True
intents.messages = True
intents.message_content = True
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
conversation_history = {}

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

# --- 起動時 ---
@bot.event
async def on_ready():
    await tree.sync()
    print(f"ログイン成功: {bot.user}")

# --- 新規参加者の挨拶 ---
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"{member.mention} ようこそ、我が主に仕える地へ……。何か困ったら気軽に声をかけてくださいね。")

# --- /mode ---
@tree.command(name="mode", description="モードを切り替えます（ご主人様専用）")
async def mode_cmd(interaction: discord.Interaction, mode: str):
    if str(interaction.user.id) != OWNER_ID:
        await interaction.response.send_message("このコマンドはご主人様専用ですわ♡", ephemeral=True)
        return

    global current_mode
    if mode in MODES:
        current_mode = mode
        await interaction.response.send_message(f"モードを『{MODES[mode]}』に変更しましたわ♡", ephemeral=True)
    else:
        await interaction.response.send_message(f"無効なモードですわ。使えるモード: {', '.join(MODES.keys())}", ephemeral=True)

# --- /quiz ---
@tree.command(name="quiz", description="クイズを出題します")
async def quiz_cmd(interaction: discord.Interaction, genre: str, difficulty: str):
    genre_data = QUIZ_DATA.get(genre)
    if not genre_data or difficulty not in genre_data:
        await interaction.response.send_message("ジャンルまたは難易度が無効ですわ、ごめんなさいね。", ephemeral=True)
        return

    quiz = random.choice(genre_data[difficulty])
    user_id = str(interaction.user.id)
    active_quizzes[user_id] = {"answer": quiz["answer"], "channel_id": interaction.channel.id}
    await interaction.user.send(f"問題ですわ♪: {quiz['question']}
※このDMに答えを返信してね♡")
    await interaction.response.send_message("クイズをDMで送信しましたわ♪", ephemeral=True)

# --- メッセージ処理 ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 許可されたチャンネルとDMのみ
    if not isinstance(message.channel, discord.DMChannel) and message.channel.id != ALLOWED_CHANNEL_ID:
        return

    user_id = str(message.author.id)

    # クイズ解答処理
    if isinstance(message.channel, discord.DMChannel) and user_id in active_quizzes:
        quiz = active_quizzes[user_id]
        answer = quiz["answer"]
        channel = bot.get_channel(quiz["channel_id"])
        if channel:
            if message.content.strip().lower() == answer.lower():
                await channel.send(f"{message.author.name} さんの回答：正解ですわ！お見事ですの♪🎉")
            else:
                await channel.send(f"{message.author.name} さんの回答：残念ですわ、不正解ですの。正解は「{answer}」でしたわよ。")
        del active_quizzes[user_id]
        return

    # Gemini応答生成
    prefix = ""
    if user_id == OWNER_ID:
        prefix = "ご主人様、承知いたしました。→ "
    else:
        mode = current_mode
        if mode == "tgif":
            prefix = "神に感謝しながらお答えいたします。→ "
        elif mode == "neet":
            prefix = "無能ですが一応お答えします……。→ "
        elif mode == "debate":
            prefix = "論理的に解説いたします。→ "
        elif mode == "roast":
            prefix = "馬鹿にも分かるように答えてやるよ。→ "
        else:
            prefix = "はいはい、また面倒な質問ね。→ "

    prompt = prefix + message.content

    # コンテキスト記憶
    history = conversation_history.get(user_id, [])
    history.append({"role": "user", "parts": [prompt]})
    if len(history) > 5:
        history = history[-5:]

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_content(history))
        text = response.text

        # フィリピン/日本の天気質問への代表的な回答処理
        lowered = message.content.lower()
        if "日本の天気" in lowered or "日本の天気は" in lowered:
            text = "日本の代表として東京の天気をお伝えします。
" + text.split("
")[0]
        elif "フィリピンの天気" in lowered or "フィリピンの天気は" in lowered:
            text = "フィリピンの代表としてセブの天気をお伝えします。
" + text.split("
")[0]

        text = text.replace("にゃん♡", "").replace("にゃん", "")
        if len(text) > 2000:
            text = text[:1997] + "..."

        await message.channel.send(text)
        conversation_history[user_id] = history
    except Exception:
        traceback.print_exc()
        await message.channel.send("応答に失敗しましたわ、ごめんなさい。")

    await bot.process_commands(message)

# --- 実行 ---
keep_alive()
bot.run(TOKEN)
