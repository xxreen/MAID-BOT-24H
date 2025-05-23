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
import re

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

# --- 禁止用語リスト ---
BANNED_WORDS = ["クソ", "ばか", "死ね", "氏ね", "殺す"]

# --- モード設定 ---
MODES = {
    "default": "毒舌AIモード",
    "neet": "ニートモード（自虐）",
    "debate": "論破モード",
    "roast": "超絶煽りモード",
    "tgif": "神崇拝モード（感謝）"
}
current_mode = "default"
conversation_history = {}

# --- クイズ管理用変数 ---
active_quiz = None
quiz_lock = asyncio.Lock()

# --- クイズ問題データ ---
QUIZ_QUESTIONS = {
    "アニメ": {
        "easy": [
            {"q": "ドラえもんの秘密道具で『どこでもドア』の用途は？", "a": "どこへでも行けるドア"},
            {"q": "ナルトの忍者の里はどこ？", "a": "木ノ葉隠れの里"},
        ],
        "normal": [
            {"q": "進撃の巨人で主人公の名前は？", "a": "エレン・イェーガー"},
            {"q": "ワンピースの麦わらの一味の船長は？", "a": "モンキー・D・ルフィ"},
        ],
        "hard": [
            {"q": "コードギアスの主人公の名前は？", "a": "ルルーシュ・ランペルージ"},
            {"q": "シュタインズ・ゲートのタイムリープ装置の名前は？", "a": "電話レンジ"},
        ],
    },
    "国語": {
        "easy": [
            {"q": "『春』という漢字は何画でしょう？", "a": "9"},
            {"q": "『ありがとう』の意味は？", "a": "感謝"},
        ],
        "normal": [
            {"q": "『花鳥風月』の意味は？", "a": "自然の美しさ"},
            {"q": "『以心伝心』とは何を意味する？", "a": "言葉を使わず心が通じ合うこと"},
        ],
        "hard": [
            {"q": "『枕草子』の作者は？", "a": "清少納言"},
            {"q": "『徒然草』を書いた人物は？", "a": "兼好法師"},
        ],
    },
    "数学": {
        "easy": [
            {"q": "1+1は？", "a": "2"},
            {"q": "三角形の内角の和は？", "a": "180度"},
        ],
        "normal": [
            {"q": "微分の基本公式の一つを答えよ。", "a": "d/dx x^n = n x^(n-1)"},
            {"q": "円周率の近似値は？", "a": "3.14"},
        ],
        "hard": [
            {"q": "フェルマーの最終定理を簡単に説明せよ。", "a": "n>2の自然数でa^n + b^n = c^nの整数解はない"},
            {"q": "リーマン予想は何に関する問題？", "a": "ゼータ関数の零点"},
        ],
    },
    "社会": {
        "easy": [
            {"q": "日本の首都は？", "a": "東京"},
            {"q": "日本の通貨単位は？", "a": "円"},
        ],
        "normal": [
            {"q": "日本の国会は何院制？", "a": "二院制"},
            {"q": "日本の三権分立を答えよ。", "a": "立法、司法、行政"},
        ],
        "hard": [
            {"q": "明治維新は何年に始まった？", "a": "1868"},
            {"q": "戦後の日本国憲法の施行日は？", "a": "1947年5月3日"},
        ],
    },
    "理科": {
        "easy": [
            {"q": "水の化学式は？", "a": "H2O"},
            {"q": "光の速さは約何km/s？", "a": "30万km/s"},
        ],
        "normal": [
            {"q": "原子番号とは何を示す？", "a": "陽子の数"},
            {"q": "地球の大気の主成分は？", "a": "窒素"},
        ],
        "hard": [
            {"q": "ニュートンの運動の第三法則は？", "a": "作用・反作用の法則"},
            {"q": "DNAの二重らせん構造を発見した人物は？", "a": "ワトソンとクリック"},
        ],
    },
    "地理": {
        "easy": [
            {"q": "日本は何大陸にある？", "a": "アジア"},
            {"q": "富士山の高さは？", "a": "3776m"},
        ],
        "normal": [
            {"q": "世界で一番大きい砂漠は？", "a": "サハラ砂漠"},
            {"q": "ナイル川はどの大陸にある？", "a": "アフリカ"},
        ],
        "hard": [
            {"q": "世界の首都で標高が最も高いのは？", "a": "ラパス"},
            {"q": "ロッキー山脈はどこの国にある？", "a": "アメリカ"},
        ],
    },
    "歴史": {
        "easy": [
            {"q": "織田信長はどの時代の人物？", "a": "戦国時代"},
            {"q": "第二次世界大戦はいつ終わった？", "a": "1945年"},
        ],
        "normal": [
            {"q": "明治維新の中心人物の一人は？", "a": "西郷隆盛"},
            {"q": "江戸幕府を開いたのは？", "a": "徳川家康"},
        ],
        "hard": [
            {"q": "ペリー来航は何年？", "a": "1853年"},
            {"q": "関ヶ原の戦いで勝利した大名は？", "a": "徳川家康"},
        ],
    },
}

# --- 天気取得関数 ---
async def get_weather(city_name: str):
    if not OPENWEATHERMAP_API_KEY:
        return "天気APIキーが設定されてません。"
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

# --- テキスト短縮関数 ---
def shorten_text(text: str, max_len: int = 200):
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."

# --- 天気キーワード抽出 ---
def extract_city_from_weather_query(text: str):
    pattern = re.compile(r"([^\s]+)の天気")
    match = pattern.search(text)
    if match:
        city = match.group(1).strip()
        return city
    return None

# --- にゃん完全除去 ---
def remove_nyan(text: str):
    return re.sub(r"にゃん[♡]*|にゃーん", "", text)

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

# --- /mode コマンド ---
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

# --- /quiz コマンド ---
@tree.command(name="quiz", description="クイズを出題します")
async def quiz_cmd(interaction: discord.Interaction, genre: str, difficulty: str):
    if interaction.channel.id != ALLOWED_CHANNEL_ID:
        await interaction.response.send_message(f"このコマンドは指定チャンネル（ID: {ALLOWED_CHANNEL_ID}）でのみ使えます。", ephemeral=True)
        return

    genre = genre.strip()
    difficulty = difficulty.strip()

    if genre not in QUIZ_QUESTIONS:
        await interaction.response.send_message(f"ジャンルは次の中から選んでください: {', '.join(QUIZ_QUESTIONS.keys())}", ephemeral=True)
        return
    if difficulty not in ["easy", "normal", "hard"]:
        await interaction.response.send_message("難易度は easy, normal, hard のいずれかを指定してください。", ephemeral=True)
        return

    global active_quiz

    async with quiz_lock:
        if active_quiz is not None:
            await interaction.response.send_message("現在他のクイズが進行中です。終了までお待ちください。", ephemeral=True)
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

        # チャンネルにメンションつきで出題
        await interaction.response.send_message(f"クイズを出題します！ジャンル：{genre} 難易度：{difficulty}\n"
                                                f"{interaction.channel.mention} みんな！答えをDMで送ってね！\n"
                                                f"問題：{active_quiz['question']}")

# --- DMでの回答受付 ---
@bot.event
async def on_message(message):
    # Bot自身のメッセージは無視
    if message.author.bot:
        return

    # クイズ回答処理（DM限定）
    global active_quiz

    if isinstance(message.channel, discord.DMChannel) and active_quiz is not None:
        async with quiz_lock:
            # 回答者が既に回答済みか確認
            if message.author.id in active_quiz["answered_users"]:
                await message.channel.send("あなたは既に回答済みです。次の問題をお待ちください。")
                return

            # 正誤判定（単純な比較、前後空白無視、小文字化も考慮）
            user_answer = message.content.strip().lower()
            correct_answer = active_quiz["answer"].strip().lower()

            if user_answer == correct_answer:
                result = "正解！お見事ですわ♡"
            else:
                result = f"残念、不正解です… 正しい答えは「{active_quiz['answer']}」でした。"

            active_quiz["answered_users"].add(message.author.id)

            # DM返信
            await message.channel.send(result)

            # 出題チャンネルに結果を送信
            channel = bot.get_channel(active_quiz["channel_id"])
            if channel:
                await channel.send(f"{message.author.mention} さんの回答: {message.content}\n結果: {result}")

            # もし全員が回答済み（もしくは任意で1回答で終了）ならクイズ終了（ここでは1人回答で終了しない）
            # active_quiz = None  # 連続問題はここでクリアしない

    else:
        # 他のメッセージは通常処理に流す（ここに既存のBot応答処理など入れる）
        await bot.process_commands(message)

# --- /weather コマンド ---
@tree.command(name="weather", description="天気を調べます")
async def weather_cmd(interaction: discord.Interaction, query: str):
    city = extract_city_from_weather_query(query)
    if city is None:
        await interaction.response.send_message("「○○の天気」の形式で入力してください。", ephemeral=True)
        return
    weather_info = await get_weather(city)
    await interaction.response.send_message(weather_info)

# --- Bot起動 ---
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
