import os
import random
import time
import asyncio
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
import google.generativeai as genai

# Flaskサーバー
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# 環境変数
DISCORD_TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = "1016316997086216222"
TARGET_CHANNEL_ID = 1374589955996778577

# Gemini設定
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-1.5-flash")

# Bot初期化
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

tree = bot.tree

user_modes = {}
user_memory = {}
user_last_request = {}
COOLDOWN_SECONDS = 5

MODES = {
    "default": "毒舌AIモード",
    "neet": "ニートモード（自虐）",
    "debate": "論破モード",
    "roast": "超絶煽りモード",
    "tgif": "神崇拝モード（感謝）"
}

QUIZZES = {
    "anime": {
        "easy": ["アニメ『ドラえもん』で未来から来た猫型ロボットの名前は？|ドラえもん"],
        "normal": ["アニメ『進撃の巨人』で巨人化する主人公の名前は？|エレン"],
        "hard": ["アニメ『シュタインズ・ゲート』で使われた電話レンジ(仮)の正体は？|タイムマシン"],
    },
    "math": {
        "easy": ["1+1は？|2"],
        "normal": ["√49は？|7"],
        "hard": ["eの自然対数は？|1"],
    },
    "japanese": {
        "easy": ["「ありがとう」の丁寧な言い方は？|ありがとうございます"],
        "normal": ["『走れメロス』の作者は？|太宰治"],
        "hard": ["『枕草子』の作者は？|清少納言"],
    },
    "science": {
        "easy": ["水の化学式は？|H2O"],
        "normal": ["太陽の主な構成元素は？|水素"],
        "hard": ["光速はおよそ何m/s？|3×10^8"],
    },
    "social": {
        "easy": ["日本の首都は？|東京"],
        "normal": ["明治維新は何年？|1868"],
        "hard": ["大化の改新が起こった年は？|645"],
    }
}

@tree.command(name="mode", description="モードを切り替えます")
@discord.app_commands.describe(mode_name="default, neet, debate, roast, tgif")
async def mode(interaction: discord.Interaction, mode_name: str):
    if mode_name in MODES:
        user_modes[str(interaction.user.id)] = mode_name
        await interaction.response.send_message(f"{MODES[mode_name]}に切り替えました。")
    else:
        await interaction.response.send_message("モードが無効です。default, neet, debate, roast, tgifから選んでください。")

@tree.command(name="quiz", description="ジャンルと難易度を選んでクイズに挑戦！")
@discord.app_commands.describe(genre="anime, math, japanese, science, social", difficulty="easy, normal, hard")
async def quiz(interaction: discord.Interaction, genre: str, difficulty: str):
    genre = genre.lower()
    difficulty = difficulty.lower()
    if genre in QUIZZES and difficulty in QUIZZES[genre]:
        q_and_a = random.choice(QUIZZES[genre][difficulty])
        q, a = q_and_a.split("|")
        await interaction.response.send_message(f"**クイズ ({genre}/{difficulty})**\n{q}\n答えはDMで送ってね！")
    else:
        await interaction.response.send_message("ジャンルまたは難易度が無効です。")

async def generate_response(message_content: str, user_id: str, author: str):
    now = time.time()
    if user_id in user_last_request and now - user_last_request[user_id] < COOLDOWN_SECONDS:
        return "クールダウン中です、ちょっと待ってね。"
    user_last_request[user_id] = now

    memory = user_memory.get(user_id, [])
    memory.append(f"{author}: {message_content}")
    user_memory[user_id] = memory[-10:]

    mode = user_modes.get(user_id, "default")

    if user_id == OWNER_ID:
        prompt = f"あなたは甘々な従順キャラの女の子。ご主人様からの指示：{message_content}\nあなた:"
    elif mode == "neet":
        prompt = f"あなたはニートで自虐的。内容：{message_content}\nあなた:"
    elif mode == "debate":
        prompt = f"あなたは論破大好きなAI。相手：{message_content}\nあなた:"
    elif mode == "roast":
        prompt = f"あなたは皮肉と煽り全開のAI。発言：{message_content}\nあなた:"
    elif mode == "tgif":
        prompt = f"あなたは神を崇拝し、全てに感謝するAI。会話内容：{message_content}\nあなた:"
    else:
        prompt = f"あなたは毒舌で皮肉屋。発言：{message_content}\nあなた:"

    try:
        response = await asyncio.to_thread(model.generate_content, [prompt])
        return response.text.strip()
    except Exception as e:
        print("Geminiエラー:", e)
        return "AIが調整中みたい。しばらくしてからもう一度お願い。"

@bot.event
async def on_message(message):
    if message.author.bot or message.channel.id != TARGET_CHANNEL_ID:
        return
    await bot.process_commands(message)
    response = await generate_response(message.content, str(message.author.id), message.author.name)
    await message.channel.send(response)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ ログイン成功: {bot.user}")

bot.run(DISCORD_TOKEN)
