import discord
from discord.ext import commands
import os
import random
from flask import Flask
from threading import Thread
import google.generativeai as genai
import asyncio
import traceback
import difflib
import aiohttp

# --- 環境変数から読み込み ---
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

# --- モード設定 ---
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

# --- クイズデータ ---
QUIZ_DATA = {
    "アニメ": {
        "easy": [
            {"question": "『ドラゴンボール』の主人公は誰？", "answer": "孫悟空"},
            {"question": "『ポケモン』のピカチュウの進化前の姿は？", "answer": "ピチュー"}
        ],
        "normal": [
            {"question": "『ワンピース』の麦わらの一味の船長は？", "answer": "モンキー・D・ルフィ"},
            {"question": "『ナルト』の主人公の名前は？", "answer": "うずまきナルト"}
        ],
        "hard": [
            {"question": "『新世紀エヴァンゲリオン』の主人公は？", "answer": "碇シンジ"},
            {"question": "『コードギアス』の主人公は？", "answer": "ルルーシュ・ランペルージ"}
        ]
    },
    "数学": {
        "easy": [
            {"question": "1+1は？", "answer": "2"},
            {"question": "3×3は？", "answer": "9"}
        ],
        "normal": [
            {"question": "√16は？", "answer": "4"},
            {"question": "2の3乗は？", "answer": "8"}
        ],
        "hard": [
            {"question": "微分の定義は？", "answer": "極限を用いて関数の変化率を求めること"},
            {"question": "積分定数は何と呼ばれる？", "answer": "積分定数"}
        ]
    },
    "社会": {
        "easy": [
            {"question": "日本の首都は？", "answer": "東京"},
            {"question": "日本の通貨単位は？", "answer": "円"}
        ],
        "normal": [
            {"question": "日本の天皇の名前は？", "answer": "徳仁"},
            {"question": "日本の国会は何院制？", "answer": "二院制"}
        ],
        "hard": [
            {"question": "日本の三権分立の三つは？", "answer": "立法、行政、司法"},
            {"question": "1945年に終戦した戦争は？", "answer": "第二次世界大戦"}
        ]
    },
    "理科": {
        "easy": [
            {"question": "水の化学式は？", "answer": "H2O"},
            {"question": "地球は何番目の惑星？", "answer": "3"}
        ],
        "normal": [
            {"question": "光の速度は約何km/s？", "answer": "30万"},
            {"question": "元素記号でOは何？", "answer": "酸素"}
        ],
        "hard": [
            {"question": "ニュートンの運動の第2法則は？", "answer": "F=ma"},
            {"question": "DNAの正式名称は？", "answer": "デオキシリボ核酸"}
        ]
    },
    "地理": {
        "easy": [
            {"question": "日本で一番高い山は？", "answer": "富士山"},
            {"question": "アメリカの首都は？", "answer": "ワシントンD.C."}
        ],
        "normal": [
            {"question": "世界で一番大きい砂漠は？", "answer": "サハラ砂漠"},
            {"question": "日本の最北端の島は？", "answer": "宗谷岬"}
        ],
        "hard": [
            {"question": "ユーラシア大陸の最南端は？", "answer": "ケープ・ロス"},
            {"question": "アフリカの最大の湖は？", "answer": "ビクトリア湖"}
        ]
    },
    "歴史": {
        "easy": [
            {"question": "織田信長は何時代の武将？", "answer": "戦国時代"},
            {"question": "明治維新は何年に始まった？", "answer": "1868"}
        ],
        "normal": [
            {"question": "鎌倉幕府を開いたのは誰？", "answer": "源頼朝"},
            {"question": "江戸時代の将軍は何家？", "answer": "徳川家"}
        ],
        "hard": [
            {"question": "関ヶ原の戦いは何年？", "answer": "1600"},
            {"question": "大正時代は何年から何年？", "answer": "1912-1926"}
        ]
    }
}

# --- 類似度判定関数 ---
def is_answer_correct(user_answer: str, correct_answer: str, threshold=0.7):
    user_answer_norm = user_answer.lower().replace(" ", "").replace("　", "")
    correct_answer_norm = correct_answer.lower().replace(" ", "").replace("　", "")
    ratio = difflib.SequenceMatcher(None, user_answer_norm, correct_answer_norm).ratio()
    return ratio >= threshold

# --- 天気取得関数 ---
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
            return (f"{city_name} の天気:\n"
                    f"天気: {weather_desc}\n"
                    f"気温: {temp}℃\n"
                    f"湿度: {humidity}%\n"
                    f"風速: {wind_speed} m/s")

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

# --- /mode ---（ご主人様専用）
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

# --- /quiz --- クイズ出題
@tree.command(name="quiz", description="クイズを出題します")
async def quiz_cmd(interaction: discord.Interaction, genre: str, difficulty: str):
    genre_data = QUIZ_DATA.get(genre)
    if not genre_data or difficulty not in genre_data:
        await interaction.response.send_message("ジャンルまたは難易度が無効ですわ、ごめんなさいね。", ephemeral=True)
        return
    quiz = random.choice(genre_data[difficulty])
    user_id = str(interaction.user.id)
    active_quizzes[user_id] = {"answer": quiz["answer"], "channel_id": interaction.channel.id}
    channel = bot.get_channel(ALLOWED_CHANNEL_ID)
    if channel:
        await channel.send(f"{interaction.user.mention} さん、問題ですわ♪: {quiz['question']}")
    await interaction.user.send(f"問題ですわ♪: {quiz['question']}\n※このDMに答えを返信してね♡")
    await interaction.response.send_message("クイズを出題しましたわ♪", ephemeral=True)

# --- メッセージ処理 ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # 許可されたチャンネルかDMのみ
    if not isinstance(message.channel, discord.DMChannel) and message.channel.id != ALLOWED_CHANNEL_ID:
        return
    user_id = str(message.author.id)
    # クイズ解答処理（DM）
    if isinstance(message.channel, discord.DMChannel) and user_id in active_quizzes:
        quiz = active_quizzes[user_id]
        answer = quiz["answer"]
        channel = bot.get_channel(quiz["channel_id"])
        if channel:
            if is_answer_correct(message.content.strip(), answer):
                await channel.send(f"{message.author.name} さんの回答：正解ですわ！お見事ですの♪🎉")
            else:
                await channel.send(f"{message.author.name} さんの回答：残念ですわ、不正解ですの。正解は「{answer}」でしたわよ。")
        del active_quizzes[user_id]
        return

    # Gemini応答生成（元々の会話機能）
    user_id = str(message.author.id)
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
            text = response.text
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
