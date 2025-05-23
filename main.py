import discord
from discord.ext import commands
import os
import asyncio
import google.generativeai as genai
from flask import Flask
from threading import Thread

# --- 環境変数 ---
DISCORD_TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

OWNER_ID = 1016316997086216222
TARGET_CHANNEL_ID = 1374589955996778577

# --- Gemini設定 ---
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
bot = commands.Bot(command_prefix="/", intents=intents)

# --- モード管理 ---
user_modes = {}
MODES = {
    "default": "毒舌AIモード",
    "neet": "ニートモード",
    "debate": "論破モード",
    "roast": "超絶煽りモード",
    "tgif": "神崇拝モード",
}

# --- モード切替 ---
@bot.slash_command(name="mode", description="モードを切り替えます")
async def mode(ctx: discord.ApplicationContext, mode_name: discord.Option(str, "モードを選択", choices=list(MODES.keys()))):
    user_modes[ctx.author.id] = mode_name
    await ctx.respond(f"モードを『{MODES[mode_name]}』に切り替えました。")

# --- 会話履歴 ---
user_last_request = {}
user_memory = {}
COOLDOWN_SECONDS = 5

async def generate_response(message_content: str, author_id: int, author_name: str) -> str:
    import time
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
        # Gemini API呼び出しは同期処理のため非同期でスレッド実行
        response = await asyncio.to_thread(model.generate_content, [prompt])
        return response.text.strip()
    except Exception as e:
        print("Geminiエラー:", e)
        return "エラーが発生しました。GEMINIが休憩中かもしれません。"

# --- メッセージ受信 ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.channel.id != TARGET_CHANNEL_ID:
        return
    if message.content.startswith("/"):
        await bot.process_commands(message)
        return

    reply = await generate_response(message.content, message.author.id, message.author.name)
    await message.channel.send(reply)

# --- 起動処理 ---
@bot.event
async def on_ready():
    print(f"{bot.user} でログインしました。")
    print("Botが起動しました。")

# --- メイン ---
if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
