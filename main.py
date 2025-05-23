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

# --- 禁止用語リスト（今はチェック無効化） ---
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

# --- メッセージ処理 ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 許可されたチャンネルとDMのみ対応
    if not isinstance(message.channel, discord.DMChannel) and message.channel.id != ALLOWED_CHANNEL_ID:
        return

    user_id = str(message.author.id)
    content = message.content.strip()

    # 禁止用語チェックは無効化（禁止用語OKにするため）
    # if contains_banned_word(content):
    #     await message.channel.send("禁止用語が含まれているため応答できません。お控えください。")
    #     return

    # 天気情報チェック
    city = extract_city_from_weather_query(content)
    if city:
        weather_text = await get_weather(city)
        await message.channel.send(weather_text)
        return

    # Gemini応答生成
    prefix = ""
    if user_id == OWNER_ID:
        prefix = "ご主人様、承知いたしました。→ "
    else:
        mode = current_mode
        # 禁止用語OKで毒舌指示を追加
        if mode == "default":  # 毒舌AIモード
            prefix = "毒舌で、禁止用語も遠慮なく使って答えてください。→ "
        elif mode == "roast":  # 超絶煽りモード
            prefix = "めちゃくちゃ煽って、禁止用語もガンガン使って答えてください。→ "
        elif mode == "tgif":
            prefix = "神に感謝しながらお答えします。→ "
        elif mode == "neet":
            prefix = "無能だけど答える……→ "
        elif mode == "debate":
            prefix = "論理的に言うと→ "
        else:
            prefix = "はいはい面倒だな→ "

    prompt = prefix + content

    # コンテキスト記憶
    history = conversation_history.get(user_id, [])
    history.append({"role": "user", "parts": [prompt]})
    if len(history) > 5:
        history = history[-5:]

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_content(history))
        text = response.text

        # にゃん完全除去
        text = remove_nyan(text)

        # ご主人様以外は短くする
        if user_id != OWNER_ID:
            text = shorten_text(text, max_len=150)

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
