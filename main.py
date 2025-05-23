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
        "easy": [
            {"question": "『ドラゴンボール』の主人公は誰？", "answer": "孫悟空"},
            {"question": "『ポケモン』のピカチュウの進化前の姿は？", "answer": "ピチュー"}
        ],
        "normal": [
            {"question": "『進撃の巨人』で巨人化できる主人公の名前は？", "answer": "エレン・イェーガー"},
            {"question": "『ワンピース』の主人公は？", "answer": "モンキー・D・ルフィ"}
        ],
        "hard": [
            {"question": "『銀魂』の主人公は？", "answer": "坂田銀時"},
            {"question": "『ナルト』でうずまきナルトの師匠は？", "answer": "ジライヤ"}
        ]
    },
    "数学": {
        "easy": [
            {"question": "1+1は？", "answer": "2"},
            {"question": "3×3は？", "answer": "9"}
        ],
        "normal": [
            {"question": "2の3乗は？", "answer": "8"},
            {"question": "平方根64は？", "answer": "8"}
        ],
        "hard": [
            {"question": "円周率の近似値（小数点以下2桁）を答えよ。", "answer": "3.14"},
            {"question": "三角関数のsin90度の値は？", "answer": "1"}
        ]
    },
    "社会": {
        "easy": [
            {"question": "日本の首都は？", "answer": "東京"},
            {"question": "アメリカ合衆国の大統領の名前は？", "answer": "バイデン"}
        ],
        "normal": [
            {"question": "日本の国会は衆議院と何院で構成されている？", "answer": "参議院"},
            {"question": "EUの本部がある都市は？", "answer": "ブリュッセル"}
        ],
        "hard": [
            {"question": "国連の正式名称は？", "answer": "国際連合"},
            {"question": "日本の元号で平成の前は？", "answer": "昭和"}
        ]
    },
    "理科": {
        "easy": [
            {"question": "水の化学式は？", "answer": "H2O"},
            {"question": "地球は何番目の惑星？", "answer": "3"}
        ],
        "normal": [
            {"question": "光の速度は秒速約何キロ？", "answer": "30万"},
            {"question": "元素記号Feは何の元素？", "answer": "鉄"}
        ],
        "hard": [
            {"question": "ニュートンの運動の第1法則の別名は？", "answer": "慣性の法則"},
            {"question": "DNAの二重らせん構造を発見した科学者は？", "answer": "ワトソンとクリック"}
        ]
    },
    "地理": {
        "easy": [
            {"question": "日本の一番大きな島は？", "answer": "本州"},
            {"question": "アフリカ大陸で最も大きな国は？", "answer": "アルジェリア"}
        ],
        "normal": [
            {"question": "エベレスト山がある国は？", "answer": "ネパール"},
            {"question": "ナイル川はどの大陸を流れている？", "answer": "アフリカ"}
        ],
        "hard": [
            {"question": "ロシアの首都は？", "answer": "モスクワ"},
            {"question": "世界で一番面積の大きい国は？", "answer": "ロシア"}
        ]
    },
    "歴史": {
        "easy": [
            {"question": "徳川家康は何時代の人物？", "answer": "江戸時代"},
            {"question": "織田信長が死んだ年は？", "answer": "1582"}
        ],
        "normal": [
            {"question": "明治維新は何年に始まった？", "answer": "1868"},
            {"question": "第二次世界大戦は何年に終わった？", "answer": "1945"}
        ],
        "hard": [
            {"question": "大正時代は何年から何年まで？", "answer": "1912-1926"},
            {"question": "日本の最初の元号は？", "answer": "大化"}
        ]
    }
}

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

# --- 正誤判定関数（大文字小文字無視、空白無視、部分一致で正解判定） ---
def is_correct_answer(user_answer: str, correct_answer: str):
    ua = user_answer.replace(" ", "").lower()
    ca = correct_answer.replace(" ", "").lower()
    return ca in ua or ua in ca

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
    
    quiz_channel = bot.get_channel(ALLOWED_CHANNEL_ID)
    if quiz_channel:
        await quiz_channel.send(f"{interaction.user.mention} さんへの問題ですわ♪: {quiz['question']}")
    await interaction.user.send(f"問題ですわ♪: {quiz['question']}\n※このDMに答えを返信してね♡")
    await interaction.response.send_message("クイズを出題しましたわ♪ チャンネルとDMを確認してくださいね。", ephemeral=True)

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
        correct_answer = quiz["answer"]
        channel = bot.get_channel(quiz["channel_id"])
        if channel:
            if is_correct_answer(message.content, correct_answer):
                await channel.send(f"{message.author.name} さんの回答：正解ですわ！お見事ですの♪🎉")
            else:
                await channel.send(f"{message.author.name} さんの回答：残念ですわ、不正解ですの。正解は「{correct_answer}」でしたわよ。")
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

            # 「にゃん」削除
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
