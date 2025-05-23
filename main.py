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

OWNER_ID = "1016316997086216222"  # ご主人様ID（文字列で管理）
ALLOWED_CHANNEL_ID = 1374589955996778577  # 動作許可チャンネルID
WELCOME_CHANNEL_ID = 1370406946812854404  # 新メンバー歓迎チャンネルID

# --- Gemini初期化 ---
# APIキーがない場合は初期化をスキップ、またはエラーメッセージを出す
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash") # モデル名を指定
else:
    print("[WARN] GEMINI_API_KEY が設定されていません。Gemini API は利用できません。")
    model = None # APIキーがない場合はモデルをNoneにする

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
conversation_history = {} # この変数は現在のコードでは使われていないようです
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
        return "OpenWeatherMap API キーが設定されていません。"
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={OPENWEATHERMAP_API_KEY}&lang=ja&units=metric"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"[ERROR Weather API] HTTP Status: {resp.status}, Response: {await resp.text()}")
                    return f"ごめんなさい、{city_name}の天気情報が見つかりませんでした。"
                data = await resp.json()
                weather_desc = data['weather'][0]['description']
                temp = data['main']['temp']
                humidity = data['main']['humidity']
                wind_speed = data['wind']['speed']
                return f"{city_name}の天気: {weather_desc}, 気温: {temp}℃, 湿度: {humidity}%, 風速: {wind_speed}m/s"
        except aiohttp.ClientError as e:
            print(f"[ERROR Weather API] ネットワークエラー: {e}")
            return "ごめんなさい、天気情報の取得中にネットワークエラーが発生しました。"
        except Exception as e:
            print(f"[ERROR Weather API] 予期せぬエラー: {e}")
            return "ごめんなさい、天気情報の取得中に予期せぬエラーが発生しました。"


def extract_city_from_weather_query(text: str):
    match = re.search(r"([^\s]+)の天気", text)
    return match.group(1) if match else None

# --- Gemini返答取得 ---
async def get_gemini_reply(user_id: int, user_name: str, content: str):
    # Geminiモデルが初期化されていない場合はエラーを返す
    if model is None:
        return "ごめんなさい、Gemini API キーが設定されていないため返答できません。"

    is_owner = str(user_id) == OWNER_ID

    if is_owner:
        system_msg = (
            "あなたは優しいメイドです。ご主人様には親切で丁寧に優しく接してください。"
            "禁止用語は絶対に使わず、簡潔に答えてください。"
        )
    else:
        system_msg = (
            "あなたは毒舌なメイドです。ご主人様以外の相手には皮肉や軽い煽り、"
            "禁止用語を使ってもよいですが、過度に過激な表現は避けてください。"
            "面白く軽快な毒舌で返答してください。"
        )

    try:
        # chat() メソッドではなく start_chat() と send_message_async() を使って会話セッションを作成
        # system_msg はチャットのhistoryの先頭に役割として含める
        chat_session = model.start_chat(history=[
            {"role": "user", "parts": system_msg},
            {"role": "model", "parts": "はい、かしこまりました。"}, # モデルがシステムメッセージを理解したと仮定する応答
        ])

        # ユーザーのメッセージを送信
        response = await chat_session.send_message_async(content)
        reply = response.text
        return reply.strip()
    except genai.APIError as e:
        print(f"[ERROR Gemini API] Gemini API エラーが発生しました: {e}")
        return "ごめんなさい、Gemini API との通信に問題が発生しました。時間をおいてもう一度お試しください。"
    except Exception as e:
        print(f"[ERROR Gemini API] 予期せぬエラーが発生しました: {e}")
        return "ごめんなさい、今はうまく返せません。（内部エラー）"

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
            await interaction.response.send_message(f"モード：{MODES[mode]} に変更しました。", ephemeral=True) # メッセージを調整
        else:
            await interaction.response.send_message(f"無効なモードです。選択肢: {', '.join(MODES.keys())}", ephemeral=True)
    except Exception as e:
        print(f"[ERROR mode_cmd] {e}")

# --- クイズ補完 ---
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
            await interaction.response.send_message("このコマンドは指定チャンネルでのみ使用できます。", ephemeral=True)
            return
        if genre not in QUIZ_QUESTIONS or difficulty not in ["easy", "normal", "hard"]:
            await interaction.response.send_message("無効なジャンルまたは難易度です。", ephemeral=True)
            return

        global active_quiz
        async with quiz_lock:
            if active_quiz:
                await interaction.response.send_message("現在、他のクイズが実行中です。終了までお待ちください。", ephemeral=True)
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
            # ephemeral=False に変更
            await interaction.response.send_message(
                f"🎉 {interaction.channel.mention} みんなにクイズ！\n"
                f"📚 **ジャンル:** {genre} | ⭐ **難易度:** {difficulty}\n"
                f"❓ **問題:** {question_data['q']}\n"
                f"📢 **回答はDMで送ってね！**"
            )
    except Exception as e:
        print(f"[ERROR quiz_cmd] {e}")
        await interaction.response.send_message("クイズの開始中にエラーが発生しました。", ephemeral=True) # エラー時にも応答

# --- DMで回答受信 & 通常メッセージ処理 ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # DMでクイズ回答受付
    if isinstance(message.channel, discord.DMChannel):
        global active_quiz
        async with quiz_lock:
            if not active_quiz:
                await message.channel.send("現在、進行中のクイズはありません。")
                return
            # 回答済みのユーザーかを文字列で比較
            if str(message.author.id) in active_quiz["answered_users"]:
                await message.channel.send("あなたはすでにこのクイズに回答しています。")
                return

            user_answer = message.content.strip()
            correct_answer = active_quiz["answer"].strip()

            if user_answer.lower() == correct_answer.lower():
                result = "✨正解！おめでとうございます！🎉"
            else:
                result = f"残念、不正解です...。正解は「**{correct_answer}**」でした。"

            active_quiz["answered_users"].add(str(message.author.id))

            # クイズが出題されたチャンネルに結果を通知
            channel = bot.get_channel(active_quiz["channel_id"])
            if channel:
                await channel.send(f"{message.author.mention} さんの回答: 「{user_answer}」 → {result}")

            # 回答人数上限（例10人）に達したらクイズ終了
            # 必要に応じて変更可能
            # ここはクイズの終了条件をより柔軟にするか、タイムアウトを導入すると良い
            if len(active_quiz["answered_users"]) >= 10: # 例として10人
                active_quiz = None # クイズを終了
                if channel:
                    await channel.send("🏆 クイズ終了！たくさんのご回答ありがとうございました！またね！")

            await message.channel.send(result) # DMにも結果を返信
        return

    # チャンネルは指定チャンネル限定 (ALLOWED_CHANNEL_ID)
    if message.channel.id != ALLOWED_CHANNEL_ID:
        return

    # モードによる特殊応答
    global current_mode
    content = message.content.strip()

    # 天気問い合わせ判定
    city = extract_city_from_weather_query(content)
    if city:
        weather_info = await get_weather(city)
        await message.channel.send(weather_info)
        return

    # Gemini返答取得
    reply = await get_gemini_reply(message.author.id, str(message.author), content)

    # --- 以下のモード別文末付加部分を削除 ---
    # if current_mode == "neet":
    #     reply += "\n（ニートモードで自虐的に）"
    # elif current_mode == "debate":
    #     reply += "\n（論破モードで反論します）"
    # elif current_mode == "roast":
    #     reply += "\n（超絶煽りモードです）"
    # elif current_mode == "tgif":
    #     reply += "\n（感謝と神崇拝モード）"
    # ------------------------------------

    await message.channel.send(reply)

# --- Bot起動 ---
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
