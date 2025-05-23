import discord
from discord.ext import commands
import os
import random
from flask import Flask
from threading import Thread
import google.generativeai as genai
import asyncio
import traceback
import aiohttp

# --- 設定 ---
TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
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

intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

MODES = {
    "default": "毒舌AIモード",
    "neet": "ニートモード",
    "debate": "論破モード",
    "roast": "超絶煽りモード",
    "tgif": "神崇拝モード"
}
current_mode = "default"
active_quizzes = {}
conversation_history = {}

QUIZ_DATA = {
    "アニメ": {
        "easy": [
            {"question": "『ドラゴンボール』の主人公は誰？", "answer": "孫悟空"},
            {"question": "『ポケモン』のピカチュウの進化前は？", "answer": "ピチュー"}
        ],
        "normal": [
            {"question": "『進撃の巨人』で主人公の名前は？", "answer": "エレン"},
            {"question": "『ワンピース』でゾロのフルネームは？", "answer": "ロロノア・ゾロ"}
        ],
        "hard": [
            {"question": "『涼宮ハルヒの憂鬱』で朝比奈みくるの所属クラブは？", "answer": "文芸部"},
            {"question": "『STEINS;GATE』でダルの本名は？", "answer": "橋田至"}
        ]
    },
    "数学": {
        "easy": [
            {"question": "2+2は？", "answer": "4"},
            {"question": "3×3は？", "answer": "9"}
        ],
        "normal": [
            {"question": "12÷3は？", "answer": "4"},
            {"question": "√81 は？", "answer": "9"}
        ],
        "hard": [
            {"question": "log10(1000) は？", "answer": "3"},
            {"question": "微分: f(x)=x² の f'(x) は？", "answer": "2x"}
        ]
    }
}

async def get_weather(city_name: str):
    if not OPENWEATHERMAP_API_KEY:
        return "天気情報のAPIキーが設定されていません。"
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={OPENWEATHERMAP_API_KEY}&lang=ja&units=metric"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return f"{city_name} の天気情報が取得できませんでした。"
            data = await resp.json()
            weather_desc = data['weather'][0]['description']
            temp = data['main']['temp']
            humidity = data['main']['humidity']
            wind_speed = data['wind']['speed']
            return (f"{city_name} の天気:\n天気: {weather_desc}\n気温: {temp}℃\n湿度: {humidity}%\n風速: {wind_speed} m/s")

@bot.event
async def on_ready():
    await tree.sync()
    print(f"ログイン成功: {bot.user}")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"{member.mention} ようこそ、我が主に仕える地へ……。")

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

@tree.command(name="quiz", description="クイズを出題します")
async def quiz_cmd(interaction: discord.Interaction, genre: str, difficulty: str):
    genre_data = QUIZ_DATA.get(genre)
    if not genre_data or difficulty not in genre_data:
        await interaction.response.send_message("ジャンルまたは難易度が無効ですわ。", ephemeral=True)
        return

    quiz = random.choice(genre_data[difficulty])
    user_id = str(interaction.user.id)
    active_quizzes[user_id] = {"answer": quiz["answer"], "channel_id": ALLOWED_CHANNEL_ID}

    quiz_channel = bot.get_channel(ALLOWED_CHANNEL_ID)
    await quiz_channel.send(f"{interaction.user.mention} さんへのクイズですわ！\n**{quiz['question']}**\n※答えはDMで送ってね♡")
    await interaction.user.send(f"問題ですわ♪: {quiz['question']}\n※このDMに答えを返信してね♡")
    await interaction.response.send_message("問題をクイズチャンネルとDMに送信しましたわ♪", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not isinstance(message.channel, discord.DMChannel) and message.channel.id != ALLOWED_CHANNEL_ID:
        return

    user_id = str(message.author.id)

    if isinstance(message.channel, discord.DMChannel) and user_id in active_quizzes:
        quiz = active_quizzes[user_id]
        answer = quiz["answer"]
        channel = bot.get_channel(quiz["channel_id"])
        if channel:
            if message.content.strip().lower() == answer.lower():
                await channel.send(f"{message.author.name} さんの回答：✅ 正解ですわ！🎉")
            else:
                await channel.send(f"{message.author.name} さんの回答：❌ 不正解ですの。正解は「{answer}」でしたわ。")
        del active_quizzes[user_id]
        return

    prefix = ""
    if user_id == OWNER_ID:
        prefix = "ご主人様、承知いたしました。→ "
    else:
        mode = current_mode
        prefix = {
            "tgif": "神に感謝しながらお答えいたします。→ ",
            "neet": "無能ですが一応お答えします……。→ ",
            "debate": "論理的に解説いたします。→ ",
            "roast": "馬鹿にも分かるように答えてやるよ。→ ",
        }.get(mode, "はいはい、また面倒な質問ね。→ ")

    prompt = prefix + message.content
    history = conversation_history.get(user_id, [])
    history.append({"role": "user", "parts": [prompt]})
    if len(history) > 5:
        history = history[-5:]

    try:
        lowered = message.content.lower()
        if "日本の天気" in lowered or "東京の天気" in lowered:
            weather_text = await get_weather("Tokyo")
            await message.channel.send(weather_text)
        elif "フィリピンの天気" in lowered or "セブの天気" in lowered:
            weather_text = await get_weather("Cebu")
            await message.channel.send(weather_text)
        else:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: model.generate_content(history))
            text = response.text.replace("にゃん♡", "").replace("にゃん", "")
            await message.channel.send(text[:1997] + "..." if len(text) > 2000 else text)
            conversation_history[user_id] = history
    except Exception:
        traceback.print_exc()
        await message.channel.send("応答に失敗しましたわ、ごめんなさい。")

    await bot.process_commands(message)

keep_alive()
bot.run(TOKEN)
