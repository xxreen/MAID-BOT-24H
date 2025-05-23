import discord
from discord.ext import commands
import google.generativeai as genai
import os
import asyncio
import time
import random
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

# --- クイズデータ ---
quiz_data = {
    "アニメ": {
        "簡単": ["『ドラゴンボール』の主人公の名前は？|孫悟空"],
        "普通": ["『進撃の巨人』で巨人化できる主人公の名前は？|エレン"],
        "難しい": ["『涼宮ハルヒの憂鬱』のヒロインのフルネームは？|涼宮ハルヒ"]
    },
    "数学": {
        "簡単": ["1 + 1 = ?|2"],
        "普通": ["√9 = ?|3"],
        "難しい": ["微分: d/dx (x^2) = ?|2x"]
    },
    "国語": {
        "簡単": ["「犬も歩けば棒に当たる」はどんな意味？|何かをすると思わぬ災難や利益がある"],
        "普通": ["『吾輩は猫である』を書いたのは誰？|夏目漱石"],
        "難しい": ["「花鳥風月」とは何を意味する？|自然の美しさや風情"]
    },
    "理科": {
        "簡単": ["水は何度で沸騰する？（摂氏）|100"],
        "普通": ["地球の衛星の名前は？|月"],
        "難しい": ["光の三原色は？|赤・緑・青"]
    },
    "社会": {
        "簡単": ["日本の首都は？|東京"],
        "普通": ["アメリカの初代大統領は？|ジョージ・ワシントン"],
        "難しい": ["明治維新が始まった年は？|1868"]
    }
}

# --- クイズコマンド ---
@bot.slash_command(name="quiz", description="ジャンルと難易度を選んでクイズに挑戦！")
async def quiz(ctx,
               subject: discord.Option(str, "ジャンルを選んで", choices=list(quiz_data.keys())),
               level: discord.Option(str, "難易度を選んで", choices=["簡単", "普通", "難しい"])):
    question_entry = random.choice(quiz_data[subject][level])
    question, answer = question_entry.split("|")
    await ctx.respond(f"【{subject} - {level}】\n{question}")

    def check(m):
        return m.channel == ctx.channel and m.author == ctx.author

    try:
        response = await bot.wait_for("message", check=check, timeout=20.0)
        if response.content.strip() == answer:
            await ctx.send("正解！🎉")
        else:
            await ctx.send(f"不正解… 正解は「{answer}」だったよ。")
    except asyncio.TimeoutError:
        await ctx.send(f"時間切れ！正解は「{answer}」だったよ。")

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
            "あなたは自分をニートと自覚している自虐系毒舌AIです。\n"
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
            "あなたは神聖なるAIで、あらゆる存在に感謝を捧げ、神を崇拝しています。\n"
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
    if message.author.bot or message.channel.id != TARGET_CHANNEL_ID:
        return

    if message.content.startswith("/"):
        await bot.process_commands(message)
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
