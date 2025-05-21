import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import requests
import json
import random

# .envからTOKENとAPIキー読み込み
load_dotenv()
TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

OWNER_ID = 1016316997086216222  # ご主人様のDiscord ID（int型）
ALLOWED_CHANNEL_ID = 1374589955996778577  # Botが反応するチャンネルID（int型）

# 称号データ
DEFAULT_TITLES = {
    OWNER_ID: "天才",
}

TITLE_CONDITIONS = {
    "アニメ博士": {"quiz_correct": 10},
    "わがままご主人様": {"questions_asked": 100},
    "しりとり名人": {"shiritori_wins": 5},
}

# 難易度別クイズ問題例（アニメ特化）
QUIZ_QUESTIONS = {
    "easy": [
        {"question": "ナルトの主人公の名前は？", "answer": "うずまきナルト", "hint": "忍者の名前です"},
        {"question": "ドラゴンボールの主人公は？", "answer": "孫悟空", "hint": "サイヤ人です"},
    ],
    "medium": [
        {"question": "進撃の巨人の舞台はどんな世界？", "answer": "壁に囲まれた世界", "hint": "外は危険"},
        {"question": "ワンピースの主人公の夢は？", "answer": "海賊王になること", "hint": "海賊のトップ"},
    ],
    "hard": [
        {"question": "カウボーイビバップで主人公の名前は？", "answer": "スパイク・スピーゲル", "hint": "宇宙の賞金稼ぎ"},
        {"question": "コードギアスのルルーシュの妹の名前は？", "answer": "ナナリー", "hint": "優しい少女"},
    ],
}

class MaidBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        # 既にcommands.Botにtreeがあるので再定義禁止
        self.user_data = {}  # ユーザーデータ(名前・好み・クイズ正解数など)
        self.siritori_last_word = None
        self.siritori_turn_user = None
        self.siritori_active = False

    async def setup_hook(self):
        # スラッシュコマンドを同期
        await self.tree.sync()

    def ask_gemini_api(self, prompt_text):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text}
                    ]
                }
            ]
        }

        response = requests.post(url, headers=headers, json=data)
        result = response.json()

        print("=== Gemini API Response ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        try:
            content = result["candidates"][0]["content"]["parts"][0]["text"]
            return content
        except (KeyError, IndexError):
            return "APIのレスポンス形式が予期せぬものです。"

    def get_user_title(self, user_id):
        # デフォルト称号＋条件達成称号取得
        titles = []
        if user_id in DEFAULT_TITLES:
            titles.append(DEFAULT_TITLES[user_id])
        data = self.user_data.get(user_id, {})
        for title, cond in TITLE_CONDITIONS.items():
            matched = True
            for k, v in cond.items():
                if data.get(k, 0) < v:
                    matched = False
                    break
            if matched:
                titles.append(title)
        return titles if titles else ["なし"]

    # しりとり単語判定用（簡易）
    def valid_shiritori_word(self, word):
        # かな判定などは省略、ここではひらがなカタカナ・漢字でも許可
        if len(word) < 2:
            return False
        if word[-1] == "ん":
            return False
        return True

    async def on_ready(self):
        print(f"ログインしました: {self.user}")

    async def on_message(self, message):
        if message.author == self.user:
            return
        if message.channel.id != ALLOWED_CHANNEL_ID:
            return  # 指定チャンネル以外無視

        user_id = message.author.id
        content = message.content.strip()

        # 簡潔な質問以外はトークン節約のためスルー
        if not content:
            return

        # しりとりモード処理
        if self.siritori_active and user_id == self.siritori_turn_user:
            word = content
            if not self.valid_shiritori_word(word):
                await message.channel.send(f"それは使えない単語です、ご主人様。")
                return
            if self.siritori_last_word and word[0] != self.siritori_last_word[-1]:
                await message.channel.send(f"前の単語の最後の文字と繋がっていませんよ？")
                return
            if word[-1] == "ん":
                await message.channel.send(f"最後に「ん」がつきましたので、あなたの負けです。")
                self.siritori_active = False
                return
            self.siritori_last_word = word
            # BOTの返答（簡単に単語生成）
            bot_word = word[-1] + "り"  # 簡易例
            if bot_word[-1] == "ん":
                await message.channel.send(f"BOTが「ん」で終わりました。あなたの勝ちです！")
                self.siritori_active = False
                return
            self.siritori_last_word = bot_word
            self.siritori_turn_user = user_id
            await message.channel.send(f"わたくしの単語は「{bot_word}」です。続けてください！")
            return

        # 普通の会話（質問受付）
        if user_id == OWNER_ID:
            prompt = f"あなたは優しいメイドです。ご主人様に丁寧に短めに返答してください。質問：{content}"
        else:
            prompt = f"あなたは毒舌なメイドです。相手が攻撃的でなければ毒舌だけで答え、議論になれば強く反論してください。質問：{content}"

        reply = self.ask_gemini_api(prompt)
        # ユーザーデータ更新（質問数カウント）
        data = self.user_data.setdefault(user_id, {})
        data["questions_asked"] = data.get("questions_asked", 0) + 1

        await message.channel.send(reply)

    # --- スラッシュコマンド群 ---

    @app_commands.command(name="title", description="あなたの称号を表示します")
    async def title(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        titles = self.get_user_title(user_id)
        await interaction.response.send_message(f"あなたの称号: {', '.join(titles)}")

    @app_commands.command(name="fortune", description="今日のラッキーアイテムを占います")
    async def fortune(self, interaction: discord.Interaction):
        items = ["クローバー", "ペン", "猫のぬいぐるみ", "コーヒー", "星のアクセサリー"]
        item = random.choice(items)
        await interaction.response.send_message(f"今日のラッキーアイテムは「{item}」です、ご主人様。")

    @app_commands.command(name="quiz", description="アニメクイズを出題します")
    @app_commands.describe(difficulty="難易度を選んでください")
    @app_commands.choices(difficulty=[
        app_commands.Choice(name="easy", value="easy"),
        app_commands.Choice(name="medium", value="medium"),
        app_commands.Choice(name="hard", value="hard"),
    ])
    async def quiz(self, interaction: discord.Interaction, difficulty: app_commands.Choice[str]):
        user_id = interaction.user.id
        if user_id not in self.user_data:
            self.user_data[user_id] = {"quiz_correct": 0, "quiz_current": None}
        questions = QUIZ_QUESTIONS[difficulty.value]
        q = random.choice(questions)
        self.user_data[user_id]["quiz_current"] = q
        await interaction.response.send_message(f"問題: {q['question']} (ヒントがほしいときは「!hint」とチャットへ)")

    @app_commands.command(name="hint", description="クイズのヒントを表示します")
    async def hint(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        data = self.user_data.get(user_id)
        if not data or "quiz_current" not in data or data["quiz_current"] is None:
            await interaction.response.send_message("現在クイズは出題されていません。")
            return
        hint = data["quiz_current"].get("hint", "ヒントはありません。")
        await interaction.response.send_message(f"ヒント: {hint}")

    @app_commands.command(name="answer", description="クイズに回答します")
    @app_commands.describe(answer="あなたの答えを入力してください")
    async def answer(self, interaction: discord.Interaction, answer: str):
        user_id = interaction.user.id
        data = self.user_data.get(user_id)
        if not data or "quiz_current" not in data or data["quiz_current"] is None:
            await interaction.response.send_message("現在クイズは出題されていません。")
            return
        correct_answer = data["quiz_current"]["answer"]
        if answer.strip() == correct_answer:
            data["quiz_correct"] = data.get("quiz_correct", 0) + 1
            data["quiz_current"] = None
            await interaction.response.send_message("正解です！称号も増やせますよ！")
        else:
            await interaction.response.send_message("不正解です。もう一度挑戦してください。")

    @app_commands.command(name="shiritori", description="しりとりを開始します")
    async def shiritori(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if self.siritori_active:
            await interaction.response.send_message("すでにしりとりモードが開始されています。")
            return
        self.siritori_active = True
        self.siritori_last_word = None
        self.siritori_turn_user = user_id
        await interaction.response.send_message("しりとりモードを開始します。最初の単語を送ってください！")

    @app_commands.command(name="stopshiritori", description="しりとりを終了します")
    async def stopshiritori(self, interaction: discord.Interaction):
        if not self.siritori_active:
            await interaction.response.send_message("しりとりモードは開始されていません。")
            return
        self.siritori_active = False
        await interaction.response.send_message("しりとりモードを終了しました。")

    @app_commands.command(name="ask", description="メイドに質問します")
    @app_commands.describe(question="メイドに質問してください")
    async def ask(self, interaction: discord.Interaction, question: str):
        user_id = interaction.user.id
        if user_id == OWNER_ID:
            prompt = f"あなたは優しいメイドです。ご主人様に丁寧に短く返答してください。質問：{question}"
        else:
            prompt = f"あなたは毒舌なメイドです。相手が攻撃的でなければ毒舌だけで答え、議論になれば強く反論してください。質問：{question}"
        reply = self.ask_gemini_api(prompt)
        # 質問回数カウント
        data = self.user_data.setdefault(user_id, {})
        data["questions_asked"] = data.get("questions_asked", 0) + 1
        await interaction.response.send_message(reply)

bot = MaidBot()

# コマンドツリーにスラッシュコマンド登録
bot.tree.add_command(bot.title)
bot.tree.add_command(bot.fortune)
bot.tree.add_command(bot.quiz)
bot.tree.add_command(bot.hint)
bot.tree.add_command(bot.answer)
bot.tree.add_command(bot.shiritori)
bot.tree.add_command(bot.stopshiritori)
bot.tree.add_command(bot.ask)

bot.run(TOKEN)


