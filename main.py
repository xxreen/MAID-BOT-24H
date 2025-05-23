import discord
from discord.ext import commands
import google.generativeai as genai
import os
import asyncio
import time
from flask import Flask
from threading import Thread

# --- Discord & Gemini設定 ---
OWNER_ID = "1016316997086216222"
TARGET_CHANNEL_ID = 1374589955996778577

DISCORD_TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-2.5-flash")

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

# --- クイズ管理 ---
# user_id -> { 'question': str, 'answer': str, 'channel_id': int }
active_quizzes = {}

# --- モード切替コマンド ---
@bot.command()
async def mode(ctx, *, mode_name=None):
    user_id = str(ctx.author.id)
    if mode_name and mode_name in MODES:
        user_modes[user_id] = mode_name
        await ctx.send(f"モードを『{MODES[mode_name]}』に切り替えました。")
    else:
        current = MODES.get(user_modes.get(user_id, "default"))
        await ctx.send(f"現在のモードは『{current}』です。\n利用可能なモード: {', '.join(MODES.values())}")

# --- クイズ用問題データ ---
QUIZ_DATA = {
    "アニメ": {
        "簡単": [("ドラえもんの主人公の名前は？", "のび太")],
        "普通": [("ワンピースの主人公の名前は？", "ルフィ")],
        "難しい": [("進撃の巨人で調査兵団の団長の名前は？", "リヴァイ")],
    },
    "数学": {
        "簡単": [("1+1は？", "2")],
        "普通": [("2の3乗は？", "8")],
        "難しい": [("微分の記号は？", "d")],
    },
    "国語": {
        "簡単": [("『花』の読みは？", "はな")],
        "普通": [("漢字『森』の読みは？", "もり")],
        "難しい": [("『枕草子』を書いたのは誰？", "清少納言")],
    },
    "理科": {
        "簡単": [("水の化学式は？", "H2O")],
        "普通": [("地球の衛星は？", "月")],
        "難しい": [("光の速度は？", "約30万km/s")],
    },
    "社会": {
        "簡単": [("日本の首都は？", "東京")],
        "普通": [("アメリカの大統領は？", "バイデン")],
        "難しい": [("フランス革命は何年？", "1789")],
    },
}

# --- クイズコマンド ---
@bot.slash_command(name="quiz", description="ジャンルと難易度を選んでクイズに挑戦！")
@discord.option("genre", description="ジャンルを選択", choices=["アニメ", "数学", "国語", "理科", "社会"])
@discord.option("difficulty", description="難易度を選択", choices=["簡単", "普通", "難しい"])
async def quiz(ctx, genre: str, difficulty: str):
    user_id = str(ctx.author.id)
    # 問題をランダムに選択
    import random
    questions = QUIZ_DATA.get(genre, {}).get(difficulty, [])
    if not questions:
        await ctx.respond("そのジャンルまたは難易度の問題はありません。")
        return
    question, answer = random.choice(questions)

    # クイズ情報を保存
    active_quizzes[user_id] = {
        "question": question,
        "answer": answer,
        "channel_id": ctx.channel.id
    }

    await ctx.respond(f"【{genre} - {difficulty}クイズ】\n問題: {question}\n回答はDMで送ってね！")

# --- 応答生成関数（略、必要なら先程のものを使う） ---

# --- メッセージイベント ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # DMの場合 → クイズ回答処理
    if message.guild is None:
        user_id = str(message.author.id)
        if user_id not in active_quizzes:
            await message.channel.send("現在クイズは出題されていません。クイズを始めてください。")
            return

        correct_answer = active_quizzes[user_id]['answer']
        question_channel_id = active_quizzes[user_id]['channel_id']
        question_channel = bot.get_channel(question_channel_id)

        user_answer = message.content.strip()

        if user_answer == correct_answer:
            await message.channel.send("正解です！おめでとうございます🎉")
            if question_channel:
                await question_channel.send(f"<@{user_id}>さん、クイズの答えが正解でした！おめでとう🎉")
        else:
            await message.channel.send(f"残念、不正解です。正解は「{correct_answer}」です。")
            if question_channel:
                await question_channel.send(f"<@{user_id}>さん、クイズの答えが間違っていました。")

        # クイズ終了（記録削除）
        del active_quizzes[user_id]
        return

    # 通常メッセージは応答処理など
    await bot.process_commands(message)

# --- 起動イベント ---
@bot.event
async def on_ready():
    print(f"ログイン成功: {bot.user}")
    print("起動しました！")

# --- メイン起動 ---
if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
