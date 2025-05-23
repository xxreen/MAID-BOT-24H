import discord
from discord.ext import commands
import google.generativeai as genai
import os
import asyncio
import time
from flask import Flask
from threading import Thread
import random

# --- Discord & Gemini設定 ---
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

bot = commands.Bot(command_prefix="/", intents=intents)

# --- 起動イベントでスラッシュコマンドを同期 ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"ログイン成功: {bot.user}")

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

# --- モード切替スラッシュコマンド ---
@bot.tree.command(name="mode", description="Botの返答モードを切り替える")
async def mode(interaction: discord.Interaction, mode_name: str):
    if mode_name not in MODES:
        await interaction.response.send_message("無効なモード名です。")
        return
    user_modes[str(interaction.user.id)] = mode_name
    await interaction.response.send_message(f"モードを『{MODES[mode_name]}』に切り替えました。")

# --- クイズ問題集 ---
QUIZ = {
    "アニメ": {
        "簡単": [("ドラゴンボールの主人公は？", "孫悟空")],
        "普通": [("『進撃の巨人』で壁の名前を1つ答えてください。", "ウォール・マリア")],
        "難しい": [("『コードギアス』でルルーシュの仮面名は？", "ゼロ")],
    },
    "数学": {
        "簡単": [("1+1は？", "2")],
        "普通": [("三角形の内角の和は？", "180")],
        "難しい": [("微分の記号は？", "d")],
    },
    "国語": {
        "簡単": [("「犬も歩けば…」の続きは？", "棒に当たる")],
        "普通": [("枕草子を書いた人物は？", "清少納言")],
        "難しい": [("「徒然草」の作者は？", "吉田兼好")],
    },
    "理科": {
        "簡単": [("水の化学式は？", "H2O")],
        "普通": [("酸素の元素記号は？", "O")],
        "難しい": [("ニュートンの運動法則は何法則？", "3")],
    },
    "社会": {
        "簡単": [("日本の首都は？", "東京")],
        "普通": [("明治維新が起きたのは何年？", "1868")],
        "難しい": [("大政奉還を行った将軍は？", "徳川慶喜")],
    },
}

@bot.tree.command(name="quiz", description="ジャンルと難易度を選んでクイズに挑戦！")
async def quiz(
    interaction: discord.Interaction,
    genre: str,
    level: str
):
    if genre not in QUIZ or level not in QUIZ[genre]:
        await interaction.response.send_message("ジャンルまたは難易度が無効です。")
        return

    question, answer = random.choice(QUIZ[genre][level])
    await interaction.response.send_message(f"【{genre} - {level}】\n問題: {question}")

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        if answer in msg.content:
            await interaction.followup.send("正解！🎉")
        else:
            await interaction.followup.send(f"残念！正解は「{answer}」でした。")
    except asyncio.TimeoutError:
        await interaction.followup.send("時間切れ！⏰")

# --- 応答生成関数 ---
async def generate_response(message_content: str, author_id: str, author_name: str) -> str:
    now = time.time()
    if author_id in user_last_request and now - user_last_request[author_id] < COOLDOWN_SECONDS:
        return "ちょっと待ちな。クールダウン中だよ。"

    user_last_request[author_id] = now

    history = user_memory.get(author_id, [])
    history.append(f"{author_name}: {message_content}")
    user_memory[author_id] = history[-10:]

    memory_text = "\n".join(history)
    mode = user_modes.get(author_id, "default")

    if author_id == OWNER_ID:
        prompt = (
            "あなたは可愛い女の子キャラで、ご主人様に従順です。返答は甘く簡潔にしてください。\n"
            f"会話履歴:\n{memory_text}\n\nご主人様: {message_content}\nあなた:"
        )
    elif mode == "neet":
        prompt = (
            "あなたは自虐的な毒舌AIです。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )
    elif mode == "debate":
        prompt = (
            "あなたは論破モードの毒舌AIです。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )
    elif mode == "roast":
        prompt = (
            "あなたは煽りモードの毒舌AIです。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )
    elif mode == "tgif":
        prompt = (
            "あなたは神聖なるAIで、あらゆる存在に感謝し神を崇拝しています。返答は敬虔で神聖な口調にしてください。\n"
            f"会話履歴:\n{memory_text}\n\n民: {message_content}\nあなた:"
        )
    else:
        prompt = (
            "あなたは毒舌で、皮肉混じりの簡潔な返答をするAIです。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )

    try:
        response = await asyncio.to_thread(model.generate_content, [prompt])
        return response.text.strip()
    except Exception as e:
        print("Geminiエラー:", e)
        return "GEMINIがエラーを起こしてるみたい…"

# --- メッセージ応答イベント ---
@bot.event
async def on_message(message):
    if message.author.bot or message.channel.id != TARGET_CHANNEL_ID:
        return
    if message.content.startswith("/"):
        return
    reply = await generate_response(message.content, str(message.author.id), message.author.name)
    await message.channel.send(reply)

# --- メイン起動 ---
if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
