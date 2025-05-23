import discord
from discord.ext import commands
import google.generativeai as genai
import os
import asyncio
import time
from flask import Flask
from threading import Thread

# --- 設定 ---
OWNER_ID = "1016316997086216222"
TARGET_CHANNEL_ID = 1374589955996778577

DISCORD_TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-1.5-flash")

# --- Flask Webサーバー ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- Discord Bot設定 ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="/", intents=intents)

# --- 会話履歴 & モード管理 ---
user_last_request = {}
user_memory = {}
user_modes = {}
COOLDOWN_SECONDS = 5

MODES = {
    "default": "毒舌AIモード",
    "neet": "ニートモード（自虐）",
    "debate": "論破モード",
    "roast": "超絶煽りモード",
    "tgif": "神崇拝モード（感謝）",
}

# --- クイズデータ ---
QUIZ_QUESTIONS = {
    "anime": {
        "easy": [
            {"question": "ドラゴンボールの主人公は誰？", "answer": "孫悟空"},
            {"question": "ワンピースの主人公は？", "answer": "モンキー・D・ルフィ"},
        ],
        "normal": [
            {"question": "進撃の巨人で調査兵団の団長は？", "answer": "リヴァイ"},
        ],
        "hard": [
            {"question": "ナルトの主人公のフルネームは？", "answer": "うずまきナルト"},
        ],
    },
    "math": {
        "easy": [
            {"question": "2 + 2 は？", "answer": "4"},
            {"question": "5 - 3 は？", "answer": "2"},
        ],
        "normal": [
            {"question": "3の2乗はいくつ？", "answer": "9"},
        ],
        "hard": [
            {"question": "微分の公式を一つ答えて。", "answer": "d/dx"},
        ],
    },
    "japanese": {
        "easy": [
            {"question": "『ありがとう』の意味は？", "answer": "感謝"},
        ],
        "normal": [
            {"question": "俳句は何音節？", "answer": "17"},
        ],
        "hard": [
            {"question": "古典文学の代表作『源氏物語』の作者は？", "answer": "紫式部"},
        ],
    },
    "science": {
        "easy": [
            {"question": "水の化学式は？", "answer": "H2O"},
        ],
        "normal": [
            {"question": "地球の重力加速度は？", "answer": "9.8"},
        ],
        "hard": [
            {"question": "光の速さは秒速何キロ？", "answer": "30万"},
        ],
    },
    "social": {
        "easy": [
            {"question": "日本の首都は？", "answer": "東京"},
        ],
        "normal": [
            {"question": "第二次世界大戦は何年に終わった？", "answer": "1945"},
        ],
        "hard": [
            {"question": "アメリカ独立宣言は何年？", "answer": "1776"},
        ],
    },
}

# --- クイズ進行管理 ---
active_quizzes = {}  # user_id: {genre, difficulty, current_q, channel_id}

# --- モード切替スラッシュコマンド ---
@bot.tree.command(name="mode", description="モードを切り替えます")
async def mode(interaction: discord.Interaction, mode_name: str):
    user_id = str(interaction.user.id)
    if mode_name not in MODES:
        await interaction.response.send_message(f"無効なモードです。利用可能: {', '.join(MODES.keys())}", ephemeral=True)
        return
    user_modes[user_id] = mode_name
    await interaction.response.send_message(f"モードを『{MODES[mode_name]}』に切り替えました。", ephemeral=True)

# --- クイズ開始スラッシュコマンド ---
@bot.tree.command(name="quiz", description="ジャンルと難易度を選んでクイズに挑戦！")
@discord.app_commands.describe(genre="ジャンルを選択", difficulty="難易度を選択")
async def quiz(interaction: discord.Interaction, genre: str, difficulty: str):
    user_id = str(interaction.user.id)
    channel_id = interaction.channel.id
    genre = genre.lower()
    difficulty = difficulty.lower()

    if genre not in QUIZ_QUESTIONS or difficulty not in QUIZ_QUESTIONS[genre]:
        await interaction.response.send_message("ジャンルまたは難易度が無効です。", ephemeral=True)
        return

    question_list = QUIZ_QUESTIONS[genre][difficulty]
    if not question_list:
        await interaction.response.send_message("クイズが登録されていません。", ephemeral=True)
        return

    active_quizzes[user_id] = {
        "genre": genre,
        "difficulty": difficulty,
        "current_q": 0,
        "channel_id": channel_id,
        "questions": question_list,
    }

    question = question_list[0]["question"]
    await interaction.response.send_message(f"【{genre}・{difficulty}】クイズを開始します！\n質問: {question}\n答えはDMで送ってください。", ephemeral=False)

# --- DMでクイズ回答受付 ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    user_id = str(message.author.id)

    # チャンネル内メッセージはbotのコマンド処理を通す
    if message.guild:
        await bot.process_commands(message)
        return

    # DMでの処理
    if user_id not in active_quizzes:
        await message.channel.send("現在クイズは出題されていません。")
        return

    quiz = active_quizzes[user_id]
    current_index = quiz["current_q"]
    questions = quiz["questions"]
    channel_id = quiz["channel_id"]
    channel = bot.get_channel(channel_id)
    if channel is None:
        await message.channel.send("エラー: 元のチャンネルが見つかりません。")
        return

    correct_answer = questions[current_index]["answer"]

    if message.content.strip() == correct_answer:
        await message.channel.send("正解です！おめでとうございます🎉")
        await channel.send(f"<@{user_id}> さん、クイズの答えが正解でした！")
    else:
        await message.channel.send("残念、不正解です。")
        await channel.send(f"<@{user_id}> さん、クイズの答えが間違っています。正解は「{correct_answer}」です。")

    # 次の問題へ
    quiz["current_q"] += 1
    if quiz["current_q"] >= len(questions):
        await channel.send(f"<@{user_id}> さん、クイズは全問終了です！お疲れさまでした。")
        del active_quizzes[user_id]
    else:
        next_question = questions[quiz["current_q"]]["question"]
        await channel.send(f"<@{user_id}> さん、次の質問はこちらです:\n{next_question}\n答えはDMで送ってください。")

# --- 会話応答関数 ---
async def generate_response(message_content: str, author_id: str, author_name: str) -> str:
    now = time.time()
    if author_id in user_last_request and now - user_last_request[author_id] < COOLDOWN_SECONDS:
        return "ちょっと待ちな。クールダウン中だよ。"

    user_last
