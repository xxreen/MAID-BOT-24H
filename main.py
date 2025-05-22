import discord
from discord.ext import commands
import google.generativeai as genai
import os
import asyncio
import time

# --- あなたのDiscord IDとBotが応答するチャンネルIDを設定 ---
OWNER_ID = "1016316997086216222"
TARGET_CHANNEL_ID = 1374589955996778577

# --- トークン＆APIキー ---
DISCORD_TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Gemini API設定 ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# --- Bot設定 ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

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
}

# --- モード切替 ---
@bot.command()
async def mode(ctx, *, mode_name=None):
    user_id = str(ctx.author.id)
    if mode_name and mode_name in MODES:
        user_modes[user_id] = mode_name
        await ctx.send(f"モードを『{MODES[mode_name]}』に切り替えました。")
    else:
        current = MODES.get(user_modes.get(user_id, "default"))
        await ctx.send(f"現在のモードは『{current}』です。\n利用可能なモード: {', '.join(MODES.values())}")

# --- 応答生成 ---
async def generate_response(message_content: str, author_id: str, author_name: str) -> str:
    now = time.time()
    if author_id in user_last_request and now - user_last_request[author_id] < COOLDOWN_SECONDS:
        return "ちょっと待ちな。クールダウン中だよ。"

    user_last_request[author_id] = now

    history = user_memory.get(author_id, [])
    history.append(f"{author_name}: {message_content}")
    user_memory[author_id] = history[-10:]  # 直近10件だけ保存

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
        return "ちょっとエラー。もう一回頼むわ。"

# --- メッセージイベント ---
@bot.event
async def on_message(message):
    if message.author.bot or message.channel.id != TARGET_CHANNEL_ID:
        return

    await bot.process_commands(message)

    content = message.content.strip()
    if not content.startswith("/"):
        reply = await generate_response(content, str(message.author.id), message.author.name)
        await message.channel.send(reply)

# --- 起動ログ ---
@bot.event
async def on_ready():
    print(f"ログイン成功: {bot.user}")
    print("起動しました！")

# --- 起動 ---
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
