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
intents.dm_messages = True

bot = commands.Bot(command_prefix="/", intents=intents)

# --- 会話履歴 & モード管理 ---
user_last_request = {}
user_memory = {}
user_modes = {}
quiz_sessions = {}  # user_id:str -> dict(answer:str, channel_id:int)
COOLDOWN_SECONDS = 5

MODES = {
    "default": "毒舌AIモード",
    "neet": "ニートモード（自虐）",
    "debate": "論破モード",
    "roast": "超絶煽りモード",
    "tgif": "神崇拝モード（感謝）",
}

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

# --- クイズコマンド ---
@bot.command()
async def quiz(ctx, genre: str = None, difficulty: str = None):
    genre = genre.lower() if genre else ""
    difficulty = difficulty.lower() if difficulty else ""
    # シンプルにアニメジャンル・難易度別問題サンプル
    quiz_data = {
        "anime": {
            "easy": ("主人公の名前は？", "タロウ"),
            "normal": ("このアニメの制作会社は？", "スタジオジブリ"),
            "hard": ("このキャラの初登場話数は？", "12"),
        },
        "math": {
            "easy": ("2 + 2 は？", "4"),
            "normal": ("√16 は？", "4"),
            "hard": ("微分の公式は？", "d/dx"),
        },
        # 他ジャンルも同様に追加可能
    }
    if genre not in quiz_data or difficulty not in quiz_data[genre]:
        await ctx.send("ジャンルまたは難易度が無効です。例: `/quiz anime easy`")
        return
    question, answer = quiz_data[genre][difficulty]
    quiz_sessions[str(ctx.author.id)] = {"answer": answer, "channel_id": ctx.channel.id}
    await ctx.send(f"クイズ開始！質問: {question}\n答えは**DM**に送ってください。")

# --- Gemini応答生成関数 ---
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
            "あなたは自分をニートと自覚している自虐系毒舌AIです。返答は皮肉混じりで簡潔にしてください。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )
    elif mode == "debate":
        prompt = (
            "あなたは論破モードの毒舌AIです。相手の発言の矛盾点や過去の発言を利用して痛いところを突いてください。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )
    elif mode == "roast":
        prompt = (
            "あなたは超絶煽りモードの毒舌AIです。相手を論理と皮肉で叩きのめしてください。ただし暴力的脅迫やBANされる内容は禁止です。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )
    elif mode == "tgif":
        prompt = (
            "あなたは神聖なるAIで、あらゆる存在に感謝を捧げ、神を崇拝しています。返答は敬虔で神聖な口調にしてください。\n"
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
        return "しっかり返答はするものの…エラーが発生しました。GEMINIが休憩中なのかもね。"

# --- メッセージイベント ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild is None:
        # DMメッセージ受信時（クイズ答え判定）
        user_id = str(message.author.id)
        if user_id in quiz_sessions:
            session = quiz_sessions[user_id]
            correct_answer = session["answer"]
            user_answer = message.content.strip()

            channel = bot.get_channel(session["channel_id"])
            if user_answer.lower() == correct_answer.lower():
                await channel.send(f"{message.author.mention} 正解です！おめでとうございます！")
                await message.channel.send("正解です！おめでとうございます！")
                del quiz_sessions[user_id]
            else:
                await channel.send(f"{message.author.mention} 残念、不正解です。もう一度挑戦してください。")
                await message.channel.send("残念、不正解です。もう一度挑戦してください。")
        else:
            await message.channel.send("現在クイズは出題されていません。")
    else:
        # 通常チャンネルはコマンド処理とGemini応答
        if message.content.startswith("/"):
            await bot.process_commands(message)
            return

        if message.channel.id != TARGET_CHANNEL_ID:
            return

        reply = await generate_response(message.content, str(message.author.id), message.author.name)
        await message.channel.send(reply)

# --- 起動イベント ---
@bot.event
async def on_ready():
    print(f"ログイン成功: {bot.user}")
    print("起動しました！")

# --- メイン起動 ---
if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
