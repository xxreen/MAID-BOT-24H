from flask import Flask
# osモジュールは不要になりましたが、もし将来的に環境変数PORTなどを直接扱う場合は必要になるかもしれません。
# from os import environ # 不要な場合は削除してもOK

app = Flask('') # Flaskアプリケーションを初期化

# ルートURL (例: Railwayによって提供されるWebサービスURL) にアクセスがあった場合に
# 「Bot is alive!」というテキストを返します。
@app.route('/')
def home():
    return "Bot is alive!"

# RailwayではgunicornなどのWSGIサーバーで起動するため、
# app.run()を直接呼び出す必要はありません。
# gunicornがこのファイル内の 'app' オブジェクトを自動的に見つけて起動します。

