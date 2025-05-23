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

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

app = Flask(__name__)

# --- Webサーバー ---
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
user_modes = {}
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

# --- 起動時 ---
@bot.event
async def on_ready():
    await tree.sync()
    print(f"ログイン成功: {bot.user}")

# --- /modeコマンド ---
@tree.command(name="mode", description="モードを切り替えます")
async def mode_cmd(interaction: discord.Interaction, mode: str):
    user_id = str(interaction.user.id)
    if mode in MODES:
        user_modes[user_id] = mode
        await interaction.response.send_message(f"モードを『{MODES[mode]}』に変更しました。", ephemeral=True)
    else:
        current = MODES.get(user_modes.get(user_id, "default"))
        await interaction.response.send_message(f"現在のモードは『{current}』です。有効なモード: {', '.join(MODES.keys())}", ephemeral=True)

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
    await interaction.user.send(f"問題: {quiz['question']}\n※このDMに答えを返信してね！")
    await interaction.response.send_message("クイズをDMで送信しました。", ephemeral=True)

# --- メッセージ応答処理（DM・チャンネル共通） ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)

    # DMでのクイズ解答処理
    if isinstance(message.channel, discord.DMChannel) and user_id in active_quizzes:
        quiz = active_quizzes[user_id]
        answer = quiz["answer"]
        channel = bot.get_channel(quiz["channel_id"])
        if channel:
            if message.content.strip().lower() == answer.lower():
                await channel.send(f"{message.author.name} の回答：正解！🎉")
            else:
                await channel.send(f"{message.author.name} の回答：不正解！正解は「{answer}」だよ。")
        del active_quizzes[user_id]
        return

    # Gemini APIで応答
    mode = user_modes.get(user_id, "default")
    prefix = ""
    if user_id == OWNER_ID:
        prefix = ""
    else:
        if mode == "tgif":
            prefix = "神に感謝しながら、"
        elif mode == "neet":
            prefix = "俺なんかが言うのもあれだけど、"
        elif mode == "debate":
            prefix = "論破させてもらうが、"
        elif mode == "roast":
            prefix = "お前それマジで言ってる？"
        elif mode == "default":
            prefix = "は？バカかお前、"

    prompt = prefix + message.content

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, model.generate_content, prompt)
        text = response.text
        if len(text) > 2000:
            text = text[:1997] + "..."
        await message.channel.send(text)
    except Exception:
        traceback.print_exc()
        await message.channel.send("応答に失敗したよ。")

    await bot.process_commands(message)

# --- 実行 ---
keep_alive()
bot.run(TOKEN)
