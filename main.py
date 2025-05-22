import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import requests
import json
import random
import asyncio # スレッドで実行するために必要

# .envからTOKENとAPIキー読み込み
load_dotenv()
TOKEN = os.getenv("TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# APIキーが設定されているか確認
if not TOKEN:
    print("エラー: Discord BOT TOKENが設定されていません。")
    exit(1)
if not GEMINI_API_KEY:
    print("エラー: GEMINI_API_KEYが設定されていません。")
    exit(1)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

# Discord IDは数値として扱うため、文字列ではなく直接int型で記述
OWNER_ID = 1016316997086216222  # あなたのDiscord ID
ALLOWED_CHANNEL_ID = 1374589955996778577  # Botが反応するチャンネルID

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
        self.user_data = {}  # ユーザーデータ(名前・好み・クイズ正解数など)
        self.siritori_last_word = None
        self.siritori_turn_user = None
        self.siritori_active = False
        self.quiz_active_users = {} # クイズ中のユーザー管理

    async def setup_hook(self):
        # スラッシュコマンドを同期
        await self.tree.sync()
        print("スラッシュコマンドを同期しました。")

    def ask_gemini_api(self, prompt_text):
        # Gemini-2.0-flashは存在しない可能性があるので、gemini-1.5-flash または gemini-pro を推奨
        # 最新のモデル名はGoogle AI Studioのドキュメントで確認してください。
        # ここでは例として 'gemini-1.5-flash' を使用します
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7, # 応答のランダム性
                "maxOutputTokens": 200 # 最大出力トークン数
            }
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=30) # タイムアウト設定
            response.raise_for_status() # HTTPエラーがあれば例外発生

            result = response.json()

            # デバッグ用にレスポンス全体を表示
            print("=== Gemini API Response ===")
            print(json.dumps(result, indent=2, ensure_ascii=False))

            content = result["candidates"][0]["content"]["parts"][0]["text"]
            return content
        except requests.exceptions.RequestException as e:
            print(f"APIリクエストエラー: {e}")
            return "現在、APIとの通信に問題が発生しています。しばらくお待ちください。"
        except (KeyError, IndexError) as e:
            print(f"APIレスポンス解析エラー: {e}")
            print(f"受信したJSON: {json.dumps(result, indent=2, ensure_ascii=False)}")
            return "APIのレスポンス形式が予期せぬものです。開発者にご連絡ください。"


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
        # 日本語のひらがな/カタカナ/漢字を考慮した簡単なチェック
        if not word or len(word) < 1: # 単語が空でないこと、最低1文字
            return False
        if word[-1] in "んン": # 最後の文字が「ん」でないこと
            return False
        # 他にも、辞書に存在するか、同じ単語の繰り返しではないか、などのロジックを追加可能
        return True

    async def on_ready(self):
        print(f"ログインしました: {self.user.name} (ID: {self.user.id})")
        print("=============================")

    async def on_message(self, message):
        if message.author.bot: # Bot自身のメッセージには反応しない
            return
        if message.channel.id != ALLOWED_CHANNEL_ID:
            return  # 指定チャンネル以外無視

        user_id = message.author.id
        content = message.content.strip()

        # 簡潔な質問以外はトークン節約のためスルー
        if not content:
            return

        # スラッシュコマンドの処理はon_messageではなくbot.treeで処理されるため、
        # ここでは一般的なテキストメッセージと特定のキーワードにのみ反応する
        # (例: クイズの答えやしりとり)

        # しりとりモード処理
        if self.siritori_active and user_id == self.siritori_turn_user:
            word = content
            if not self.valid_shiritori_word(word):
                await message.channel.send(f"それは使えない単語です、ご主人様。")
                return
            if self.siritori_last_word and word[0] != self.siritori_last_word[-1]:
                await message.channel.send(f"前の単語の最後の文字と繋がっていませんよ？")
                return
            if word[-1] in "んン":
                await message.channel.send(f"最後に「ん」がつきましたので、あなたの負けです。")
                self.siritori_active = False
                # しりとり敗北によるペナルティなどあれば追加
                return
            
            self.siritori_last_word = word
            # BOTの返答（Gemini APIを使って単語生成を試みる、または簡易な生成）
            # ここをGeminiにするとコストがかかるので、簡易的な生成に留める
            # 例: 最後の文字が'い'なら'イルカ'など
            # より高度なAIしりとりには、単語リストやGeminiの単語生成能力をフル活用する必要あり
            
            # 簡易なBOT単語生成
            if len(word) > 0:
                last_char = word[-1]
                bot_word_candidates = {
                    'あ': ['アリ', 'アヒル'], 'い': ['イカ', 'イヌ'], 'う': ['ウサギ', 'ウシ'],
                    'え': ['エビ', 'エリマキトカゲ'], 'お': ['オオカミ', 'オウム'],
                    'か': ['カメ', 'カニ'], 'き': ['キリン', 'キツネ'], 'く': ['クマ', 'クジラ'],
                    'け': ['ケムシ', 'ケムリクサ'], 'こ': ['コアラ', 'コウモリ'],
                    # 他の文字も追加
                }
                bot_word = random.choice(bot_word_candidates.get(last_char, [last_char + "ん？"])) # デフォルトで「ん？」
                if bot_word.endswith("ん？"):
                    # もし適切な単語がなければしりとりを終了
                    await message.channel.send(f"わたくしには続く単語が見つかりませんでした。あなたの勝ちです！")
                    self.siritori_active = False
                    # しりとり勝利カウント
                    data = self.user_data.setdefault(user_id, {})
                    data["shiritori_wins"] = data.get("shiritori_wins", 0) + 1
                    return
                
                if bot_word[-1] in "んン":
                    await message.channel.send(f"わたくしが「{bot_word}」で終わりました。あなたの勝ちです！")
                    self.siritori_active = False
                    # しりとり勝利カウント
                    data = self.user_data.setdefault(user_id, {})
                    data["shiritori_wins"] = data.get("shiritori_wins", 0) + 1
                    return
                
                self.siritori_last_word = bot_word
                self.siritori_turn_user = user_id # BOTの後は再びユーザーの番
                await message.channel.send(f"わたくしの単語は「{bot_word}」です。続けてください！")
            else:
                await message.channel.send("有効な単語ではありません。")
            return

        # スラッシュコマンド以外でのクイズ回答
        # クイズモードが有効なユーザーにのみ反応
        if user_id in self.quiz_active_users and self.quiz_active_users[user_id] is not None:
            data = self.user_data.get(user_id)
            if data and "quiz_current" in data and data["quiz_current"] is not None:
                correct_answer = data["quiz_current"]["answer"]
                if content.strip() == correct_answer:
                    data["quiz_correct"] = data.get("quiz_correct", 0) + 1
                    data["quiz_current"] = None
                    self.quiz_active_users[user_id] = None # クイズ終了
                    await message.channel.send("正解です！称号も増やせますよ！")
                else:
                    await message.channel.send("不正解です。もう一度挑戦してください。")
            return

        # 一般的な会話（Gemini APIによる応答）
        # スラッシュコマンド /ask があるため、通常のメッセージでの反応は控えめにすることも検討
        # 例: メンションされた場合のみ反応、など

        if self.user.mentioned_in(message) or (message.reference and message.reference.resolved and message.reference.resolved.author == self.user):
            # BOTへのメンション、またはBOTへの返信の場合のみGeminiに尋ねる
            if user_id == OWNER_ID:
                prompt = f"あなたは優しいメイドです。ご主人様に丁寧に短めに返答してください。質問：{content}"
            else:
                prompt = f"あなたは毒舌なメイドです。相手が攻撃的でなければ毒舌だけで答え、議論になれば強く反論してください。質問：{content}"

            reply = self.ask_gemini_api(prompt)
            # ユーザーデータ更新（質問数カウント）
            data = self.user_data.setdefault(user_id, {})
            data["questions_asked"] = data.get("questions_asked", 0) + 1

            await message.channel.send(reply)
        
        await self.process_commands(message) # スラッシュコマンド以外のプレフィックスコマンドも処理する場合は必要

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
        # ユーザーデータ初期化または取得
        if user_id not in self.user_data:
            self.user_data[user_id] = {"quiz_correct": 0}
        
        # クイズ中のユーザーを管理
        self.quiz_active_users[user_id] = True 
        
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
            self.quiz_active_users[user_id] = None # クイズ終了
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

# Botインスタンスを生成
bot = MaidBot()

# コマンドツリーにスラッシュコマンド登録 (この部分は変更不要)
# @app_commands.commandデコレーターを使用しているため、bot.tree.add_commandは不要
# 修正: commands.Botのインスタンス内でコマンドが定義されている場合、
# それらは自動的にtreeに登録されるため、通常は明示的なadd_commandは不要です。
# ただし、確実性を高めるためにそのまま残しておくことも可能です。
# （今回はそのまま残しておきますが、重複している場合はエラーにならないことを確認済み）
bot.tree.add_command(bot.title)
bot.tree.add_command(bot.fortune)
bot.tree.add_command(bot.quiz)
bot.tree.add_command(bot.hint)
bot.tree.add_command(bot.answer)
bot.tree.add_command(bot.shiritori)
bot.tree.add_command(bot.stopshiritori)
bot.tree.add_command(bot.ask)

# BOTの起動処理 (直接実行されるのはこのファイルが 'bot:' プロセスとして呼ばれた時)
# このファイルが直接実行された場合のみBOTを起動
if __name__ == "__main__":
    bot.run(TOKEN)

