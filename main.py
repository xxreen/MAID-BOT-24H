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
model = genai.GenerativeModel("gemini-1p5-flash")  # 1.5 flashモデルに変更

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
}

# --- 気分チェッカー用データ ---
MOOD_RESPONSES = {
    "happy": [
        "いい感じね！今日もご主人様の笑顔を守るわ♡",
        "元気いっぱいで何よりだわ！その調子で頑張ってね！"
    ],
    "sad": [
        "そんな日もあるわよ…私が癒してあげるからね。",
        "落ち込まないで、私がそばにいるわ。"
    ],
    "angry": [
        "怒りはエネルギーの源よ、でも暴れすぎないでね。",
        "ふーん、そんなに怒ってるの？ちょっと落ち着きなさいよ。"
    ],
    "tired": [
        "無理しないでゆっくり休んでね、ご主人様。",
        "今日は早く寝るのが一番よ。"
    ],
    "default": [
        "どんな気分？ちゃんと教えてよね？",
        "元気？それとも何かあった？話してみて。"
    ],
}

# --- お料理アシスタント用データ ---
RECIPES = {
    "rice": ["おにぎり", "チャーハン", "カレーライス"],
    "egg": ["目玉焼き", "オムレツ", "だし巻き卵"],
    "chicken": ["照り焼きチキン", "チキンカレー", "鶏の唐揚げ"],
    "default": ["サラダ", "スープ", "パスタ"]
}

# --- アニメクイズ用データ ---
ANIME_QUIZ = {
    "easy": [
        {"q": "ナルトの主人公の名前は？", "a": ["ナルト", "うずまきナルト"]},
        {"q": "ドラゴンボールの主人公は？", "a": ["孫悟空", "悟空"]},
    ],
    "normal": [
        {"q": "進撃の巨人で調査兵団の団長は誰？", "a": ["リヴァイ", "リヴァイ兵長"]},
        {"q": "ワンピースの麦わらの一味の船長は？", "a": ["モンキー・D・ルフィ", "ルフィ"]},
    ],
    "hard": [
        {"q": "コードギアスでルルーシュの妹の名前は？", "a": ["ナナリー", "ナナリー・ランペルージ"]},
        {"q": "新世紀エヴァンゲリオンで使徒の名前は？（一つ答えて）", "a": ["サキエル", "ラミエル", "ゼルエル", "バルディエル", "イスラフェル", "サハクィエル"]},
    ]
}

# --- クイズ進行管理 ---
quiz_sessions = {}

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

# --- 天気コマンド例 (以前のまま残してもOK) ---
# ここに天気コマンドなどあれば入れてください

# --- 気分チェッカーコマンド ---
@bot.command()
async def mood(ctx, *, mood=None):
    if not mood:
        await ctx.send("気分を教えてね！例えば `/mood happy` とか。")
        return
    mood = mood.lower()
    responses = MOOD_RESPONSES.get(mood, MOOD_RESPONSES["default"])
    reply = random.choice(responses)
    await ctx.send(reply)

# --- お料理アシスタントコマンド ---
@bot.command()
async def recipe(ctx, *, ingredient=None):
    if not ingredient:
        await ctx.send("使いたい食材を教えてね！例: `/recipe egg`")
        return
    ingredient = ingredient.lower()
    dishes = RECIPES.get(ingredient, RECIPES["default"])
    dish = random.choice(dishes)
    await ctx.send(f"{ingredient}なら、{dish}なんてどう？簡単で美味しいわよ！")

# --- アニメクイズ開始コマンド ---
@bot.command()
async def animequiz(ctx, *, level="easy"):
    level = level.lower()
    if level not in ANIME_QUIZ:
        await ctx.send("レベルは easy, normal, hard から選んでね。例: `/animequiz easy`")
        return

    question = random.choice(ANIME_QUIZ[level])
    user_id = str(ctx.author.id)
    quiz_sessions[user_id] = {
        "question": question,
        "level": level,
        "answered": False
    }
    await ctx.send(f"【アニメクイズ・{level}】 問題: {question['q']} \n答えはチャットに打ってね！")

# --- クイズ回答受付 ---
@bot.event
async def on_message(message):
    if message.author.bot or message.channel.id != TARGET_CHANNEL_ID:
        return

    user_id = str(message.author.id)

    # クイズ回答処理
    if user_id in quiz_sessions and not quiz_sessions[user_id]["answered"]:
        session = quiz_sessions[user_id]
        correct_answers = session["question"]["a"]
        user_answer = message.content.strip().lower()

        if any(user_answer == ans.lower() for ans in correct_answers):
            await message.channel.send(f"正解！すごいわ、ご主人様！✨")
            session["answered"] = True
            quiz_sessions.pop(user_id)
            return
        else:
            await message.channel.send("違うわよ、ご主人様…もう一度考えてみて？")
            return

    await bot.process_commands(message)

    content = message.content.strip()
    if not content.startswith("/"):
        # 元の毒舌応答生成関数呼び出し
        reply = await generate_response(content, user_id, message.author.name)
        await message.channel.send(reply)

# --- 応答生成関数（変更なし） ---
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
    else:
        prompt = (
            "あなたは毒舌なAIです。短く、鋭く、そして笑えるように返してください。\n"
            f"会話履歴:\n{memory_text}\n\n相手: {message_content}\nあなた:"
        )

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        import logging
        logging.error(f"Geminiエラー: {e}")
        return "エラーが発生したわ。Geminiが休憩中かもね。"

# --- Bot起動 ---
keep_alive()
bot.run(DISCORD_TOKEN)
