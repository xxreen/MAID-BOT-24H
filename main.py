import discord
from discord.ext import commands
import os
import random
from flask import Flask
from threading import Thread
import google.generativeai as genai
import asyncio
import aiohttp
import re

# --- 環境変数取得 ---
TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
OWNER_ID = "1016316997086216222"
ALLOWED_CHANNEL_ID = 1374589955996778577
WELCOME_CHANNEL_ID = 1370406946812854404

# --- Gemini初期化 ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-1.5-flash")

# --- Flask keep_alive ---
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot running"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    Thread(target=run).start()

# --- Discord Bot初期化 ---
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# --- 各種定義 ---
MODES = {
    "default": "毒舌AIモード",
    "neet": "ニートモード（自虐）",
    "debate": "論破モード",
    "roast": "超絶煽りモード",
    "tgif": "神崇拝モード（感謝）"
}
current_mode = "default"
conversation_history = {}
active_quiz = None
quiz_lock = asyncio.Lock()

QUIZ_QUESTIONS = {
    "アニメ": {
        "easy": [{"q": "ドラえもんの秘密道具で『どこでもドア』の用途は？", "a": "どこへでも行けるドア"}],
        "normal": [{"q": "進撃の巨人で主人公の名前は？", "a": "エレン・イェーガー"}],
        "hard": [{"q": "コードギアスの主人公の名前は？", "a": "ルルーシュ・ランペルージ"}],
    },
    "国語": {
        "easy": [{"q": "『春』という漢字は何画でしょう？", "a": "9"}],
        "normal": [{"q": "『花鳥風月』の意味は？", "a": "自然の美しさ"}],
        "hard": [{"q": "『枕草子』の作者は？", "a": "清少納言"}],
    },
    "社会": {
        "easy": [{"q": "日本の首都は？", "a": "東京"}],
        "normal": [{"q": "日本の元号で平成の前は？", "a": "昭和"}],
        "hard": [{"q": "日本の国会は何院制？", "a": "二院制"}],
    },
    "理科": {
        "easy": [{"q": "水の化学式は？", "a": "H2O"}],
        "normal": [{"q": "地球の衛星は？", "a": "月"}],
        "hard": [{"q": "元素記号『Fe』は何？", "a": "鉄"}],
    },
    "地理": {
        "easy": [{"q": "富士山の高さは？", "a": "3776m"}],
        "normal": [{"q": "日本の最南端の島は？", "a": "沖ノ鳥島"}],
        "hard": [{"q": "ユーラシア大陸の最高峰は？", "a": "エベレスト"}],
    },
    "数学": {
        "easy": [{"q": "2+2は？", "a": "4"}],
        "normal": [{"q": "円周率の近似値は？", "a": "3.14"}],
        "hard": [{"q": "微分の記号は？", "a": "d"}],
    },
}

# --- 天気取得関数 ---
async def get_weather(city_name: str):
    if not OPENWEATHERMAP_API_KEY:
        return "APIキー未設定"
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={OPENWEATHERMAP_API_KEY}&lang=ja&units=metric"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return f"{city_name}の情報なし"
            data = await resp.json()
            weather_desc = data['weather'][0]['description']
            temp = data['main']['temp']
            humidity = data['main']['humidity']
            wind_speed = data['wind']['speed']
            return f"{city_name} 天気: {weather_desc} 気温: {temp}℃ 湿度: {humidity}% 風速: {wind_speed}m/s"

def extract_city_from_weather_query(text: str):
    match = re.search(r"([^\s]+)の天気", text)
    return match.group(1) if match else None

# --- Bot起動 ---
@bot.event
async def on_ready():
    try:
        await tree.sync()
        print(f"✅ Logged in as {bot.user}")
    except Exception as e:
        print(f"[ERROR on_ready] {e}")

# --- 新メンバー歓迎 ---
@bot.event
async def on_member_join(member):
    try:
        channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            await channel.send(f"{member.mention} ようこそ。")
    except Exception as e:
        print(f"[ERROR on_member_join] {e}")

# --- モード切替 ---
@tree.command(name="mode", description="モード切替（主専用）")
async def mode_cmd(interaction: discord.Interaction, mode: str):
    try:
        if str(interaction.user.id) != OWNER_ID:
            await interaction.response.send_message("主専用", ephemeral=True)
            return
        global current_mode
        if mode in MODES:
            current_mode = mode
            await interaction.response.send_message(f"モード：{MODES[mode]}", ephemeral=True)
        else:
            await interaction.response.send_message(f"無効なモード: {', '.join(MODES.keys())}", ephemeral=True)
    except Exception as e:
        print(f"[ERROR mode_cmd] {e}")

# --- クイズの補完 ---
async def genre_autocomplete(interaction: discord.Interaction, current: str):
    return [discord.app_commands.Choice(name=k, value=k)
            for k in QUIZ_QUESTIONS.keys() if current.lower() in k.lower()][:25]

async def difficulty_autocomplete(interaction: discord.Interaction, current: str):
    options = ["easy", "normal", "hard"]
    return [discord.app_commands.Choice(name=l, value=l)
            for l in options if current.lower() in l.lower()][:25]

# --- クイズコマンド ---
@tree.command(name="quiz", description="クイズ出題")
@discord.app_commands.describe(genre="ジャンル", difficulty="難易度")
@discord.app_commands.autocomplete(genre=genre_autocomplete, difficulty=difficulty_autocomplete)
async def quiz_cmd(interaction: discord.Interaction, genre: str, difficulty: str):
    try:
        if interaction.channel.id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message("指定チャンネルでのみ", ephemeral=True)
            return
        if genre not in QUIZ_QUESTIONS or difficulty not in ["easy", "normal", "hard"]:
            await interaction.response.send_message("無効なジャンルまたは難易度", ephemeral=True)
            return

        global active_quiz
        async with quiz_lock:
            if active_quiz:
                await interaction.response.send_message("他クイズ実行中", ephemeral=True)
                return

            question_data = random.choice(QUIZ_QUESTIONS[genre][difficulty])
            active_quiz = {
                "channel_id": interaction.channel.id,
                "question": question_data["q"],
                "answer": question_data["a"],
                "asker_id": interaction.user.id,
                "genre": genre,
                "difficulty": difficulty,
                "answered_users": set()
            }
            await interaction.response.send_message(
                f"{interaction.channel.mention} クイズ！答えはDMで！\n問題：{active_quiz['question']}")
    except Exception as e:
        print(f"[ERROR quiz_cmd] {e}")

# --- 天気コマンド ---
@tree.command(name="weather", description="天気情報")
async def weather_cmd(interaction: discord.Interaction, query: str):
    try:
        city = extract_city_from_weather_query(query)
        if not city:
            await interaction.response.send_message("「○○の天気」と入力", ephemeral=True)
            return
        info = await get_weather(city)
        await interaction.response.send_message(info)
    except Exception as e:
        print(f"[ERROR weather_cmd] {e}")

# --- メッセージ処理（通常会話 + クイズDM） ---
@bot.event
async def on_message(message):
    try:
        if message.author.bot:
            return

        print(f"[DEBUG] メッセージ受信: {message.content} from {message.author.name}")

        global active_quiz
        if isinstance(message.channel, discord.DMChannel) and active_quiz:
            async with quiz_lock:
                if message.author.id in active_quiz["answered_users"]:
                    await message.channel.send("回答済")
                    return

                user_answer = message.content.strip().lower()
                correct_answer = active_quiz["answer"].strip().lower()

                result = "正解" if user_answer == correct_answer else f"不正解 正：{active_quiz['answer']}"
                active_quiz["answered_users"].add(message.author.id)

                await message.channel.send(result)
                channel = bot.get_channel(active_quiz["channel_id"])
                if channel:
                    await channel.send(f"{message.author.mention} 回答: {message.content}\n結果: {result}")
        else:
            if message.channel.id == ALLOWED_CHANNEL_ID:
                prompt = f"{message.author.display_name}「{message.content}」に返答して"
                response = await model.generate_content_async(prompt)
                await message.channel.send(response.text)

        await bot.process_commands(message)

    except Exception as e:
        print(f"[ERROR on_message] {e}")

# --- 起動 ---
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
