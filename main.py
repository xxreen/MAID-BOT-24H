import discord
from discord.ext import tasks
from discord import option
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
intents.message_content = True
bot = discord.Bot(intents=intents)

# --- クールダウン & メモリ ---
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

# --- モード切替コマンド ---
@bot.slash_command(name="mode", description="モードを切り替えます")
@option("mode_name", description="変更するモードを選択", choices=list(MODES.keys()))
async def change_mode(ctx, mode_name: str):
    user_id = str(ctx.author.id)
    user_modes[user_id] = mode_name
    await ctx.respond(f"モードを『{MODES[mode_name]}』に切り替えました。")

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
            "あなたは可愛い女の子キャラで、ご主人様に従順です。\n"
            f"会話履歴:\n{memory_text}\n\nご主人様: {message_content}\nあなた:"
        )
    elif mode == "neet":
        prompt = (
            "あなたはニートで自虐的な毒舌AIです。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )
    elif mode == "debate":
        prompt = (
            "あなたは論破モードの毒舌AIです。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )
    elif mode == "roast":
        prompt = (
            "あなたは超絶煽りモードの毒舌AIです。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )
    elif mode == "tgif":
        prompt = (
            "あなたは神を崇拝し全てに感謝する神聖なAIです。\n"
            f"会話履歴:\n{memory_text}\n\n民: {message_content}\nあなた:"
        )
    else:
        prompt = (
            "あなたは毒舌で皮肉な返答をするAIです。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )

    try:
        response = await asyncio.to_thread(model.generate_content, [prompt])
        return response.text.strip()
    except Exception as e:
        print("Geminiエラー:", e)
        return "エラーが発生しました。GEMINIが休憩中かもしれません。"

# --- メッセージイベント ---
@bot.event
async def on_message(message):
    if message.author.bot or message.channel.id != TARGET_CHANNEL_ID:
        return

    reply = await generate_response(message.content, str(message.author.id), message.author.name)
    await message.channel.send(reply)

# --- クイズデータ ---
quizzes = {
    "アニメ": {
        "簡単": [("『ワンピース』で主人公の名前は？", "ルフィ")],
        "普通": [("『進撃の巨人』で巨人化できる主人公は？", "エレン")],
        "難しい": [("『涼宮ハルヒの憂鬱』でハルヒが作った団体名は？", "SOS団")],
    },
    "数学": {
        "簡単": [("2 + 2 = ?", "4")],
        "普通": [("x^2 = 9 の時、xの値は？（正の数）", "3")],
        "難しい": [("∫ x dx = ?", "0.5x^2 + C")],
    },
    "国語": {
        "簡単": [("『走れメロス』の作者は？", "太宰治")],
        "普通": [("枕草子を書いた人物は？", "清少納言")],
        "難しい": [("『源氏物語』の作者は？", "紫式部")],
    },
    "理科": {
        "簡単": [("水の化学式は？", "H2O")],
        "普通": [("植物が光合成で作る気体は？", "酸素")],
        "難しい": [("DNAの正式名称は？", "デオキシリボ核酸")],
    },
    "社会": {
        "簡単": [("日本の首都は？", "東京")],
        "普通": [("明治維新が始まった年は？", "1868")],
        "難しい": [("フランス革命が始まった年は？", "1789")],
    },
}

# --- クイズコマンド ---
@bot.slash_command(name="quiz", description="ジャンルと難易度を選んでクイズに挑戦！")
@option("ジャンル", choices=list(quizzes.keys()))
@option("難易度", choices=["簡単", "普通", "難しい"])
async def quiz(ctx, ジャンル: str, 難易度: str):
    q, a = random.choice(quizzes[ジャンル][難易度])
    await ctx.respond(f"【{ジャンル} / {難易度}】\n{q}\n答えがわかったら教えてね！ 答え: ||{a}||")

# --- 起動イベント ---
@bot.event
async def on_ready():
    print(f"ログイン成功: {bot.user}")
    print("起動しました！")

# --- メイン起動 ---
if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
