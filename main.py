import os
import random
import json
import gspread
import tweepy
import google.generativeai as genai
import logging
from datetime import datetime
import pytz

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- ここに投稿したい日本時間をすべて記述 ---
POST_TIMES_JST = [
    "07:30", "08:30", "12:05", "12:35", "17:30",
    "19:05", "20:05", "21:05", "22:05", "23:05"
]

def setup_gspread_client():
    # (この関数の内容は変更なし)
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not creds_json:
        logging.error("環境変数 'GOOGLE_SERVICE_ACCOUNT_JSON' が見つかりません。")
        raise ValueError("GoogleサービスアカウントのJSON認証情報が設定されていません。")
    creds_dict = json.loads(creds_json)
    return gspread.service_account_from_dict(creds_dict)

def get_spreadsheet_data(spreadsheet):
    # (この関数の内容は変更なし)
    articles_sheet = spreadsheet.worksheet("articles")
    all_urls = [rec['url'] for rec in articles_sheet.get_all_records()]
    log_sheet = spreadsheet.worksheet("log")
    last_tweeted_url = log_sheet.acell('A2').value
    last_tweeted_timestamp = log_sheet.acell('B2').value
    return all_urls, last_tweeted_url, last_tweeted_timestamp, log_sheet

def generate_tweet_text(article_url):
    # (この関数の内容は変更なし)
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    if not gemini_api_key: raise ValueError("環境変数 'GEMINI_API_KEY' が設定されていません。")
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-pro')
    # (promptとAPI呼び出し部分は省略)
    # ...
    #
    prompt = f"""
あなたはプロのSNSマーケターです。
以下の記事URLの内容を読み解き、X(旧Twitter)で多くのユーザーがクリックしたくなるようなツイート投稿文を、下記の【制約条件】と【出力フォーマット】に従って生成してください。
# 記事URL
{article_url}
# 制約条件
- 投稿文のテンプレート: 『{{診断タイトル}}』 いくつかの質問に答えるだけで、あなたの隠れた「{{診断でわかること}}」が明らかに。
- {{診断タイトル}}: 記事の内容から、ユーザーの興味を強く引くようなキャッチーな診断名を8文字以内で作成してください。
- {{診断でわかること}}: 記事を読むことでユーザーが得られるメリットや、明らかになる面白い事柄を10文字以内で記述してください。
- ハッシュタグ: 必須の4つ(#診断 #心理テスト #性格診断 #自己分析)に加えて、記事の内容に最も関連性が高く、多くのインプレッションが期待できるキーワードを1つ、ハッシュタグとして追加してください。
- 全てのテキストは日本語で生成してください。
- 【出力フォーマット】以外の余計な説明や前置きは一切含めないでください。
# 出力フォーマット
{{
  "tweet_text": "『{{ここに診断タイトル}}』 いくつかの質問に答えるだけで、あなたの隠れた「{{ここに診断でわかること}}」が明らかに。\\n\\n▼今すぐ診断してみる\\n{article_url}\\n\\n#診断 #心理テスト #性格診断 #自己分析 #{{ここに追加ハッシュタグ}}"
}}
"""
    try:
        response = model.generate_content(prompt)
        json_response_str = response.text.strip().replace("```json", "").replace("```", "")
        data = json.loads(json_response_str)
        return data.get("tweet_text")
    except Exception as e:
        logging.error(f"Gemini APIでの生成に失敗しました: {e}")
        return None

def post_to_x(text):
    # (この関数の内容は変更なし)
    try:
        client = tweepy.Client(
            consumer_key=os.environ.get("X_API_KEY"),
            consumer_secret=os.environ.get("X_API_KEY_SECRET"),
            access_token=os.environ.get("X_ACCESS_TOKEN"),
            access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET")
        )
        response = client.create_tweet(text=text)
        logging.info(f"ツイート成功: https://x.com/user/status/{response.data['id']}")
        return True
    except Exception as e:
        logging.error(f"ツイートに失敗しました: {e}")
        return False


def main():
    """メイン処理"""
    # --- 1. 時間のチェック ---
    jst = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.now(jst)
    current_time_str = now_jst.strftime("%H:%M")

    if current_time_str not in POST_TIMES_JST:
        logging.info(f"現在時刻 {current_time_str} は投稿時間外です。処理をスキップします。")
        return

    try:
        spreadsheet_name = os.environ.get('SPREADSHEET_NAME')
        if not spreadsheet_name: raise ValueError("環境変数 'SPREADSHEET_NAME' が設定されていません。")

        # --- 2. スプレッドシートからデータを取得 ---
        client = setup_gspread_client()
        spreadsheet = client.open(spreadsheet_name)
        all_urls, last_url, last_ts, log_sheet = get_spreadsheet_data(spreadsheet)

        # --- 3. 重複投稿のチェック ---
        if last_ts:
            last_post_time = datetime.strptime(last_ts, '%Y-%m-%d %H:%M:%S').astimezone(jst)
            # 同じ時間帯（時・分が同じ）に既に投稿済みかチェック
            if last_post_time.strftime("%H:%M") == current_time_str and last_post_time.date() == now_jst.date():
                logging.warning(f"時間帯 {current_time_str} には既に投稿済みです。処理をスキップします。")
                return

        if not all_urls:
            logging.warning("投稿対象の記事がありません。")
            return
        
        logging.info(f"投稿時間 {current_time_str} の処理を開始します。")

        # --- 4. 投稿内容の決定と実行 ---
        candidate_urls = [url for url in all_urls if url != last_url]
        if not candidate_urls: candidate_urls = all_urls
        
        selected_url = random.choice(candidate_urls)
        tweet_text = generate_tweet_text(selected_url)
        if not tweet_text: raise RuntimeError("投稿文の生成に失敗しました。")
        
        is_success = post_to_x(tweet_text)
        
        # --- 5. ログの更新 ---
        if is_success:
            log_sheet.update('A2', selected_url)
            log_sheet.update('B2', now_jst.strftime('%Y-%m-%d %H:%M:%S'))
            logging.info(f"ログシートを更新しました。")
        else:
            raise RuntimeError("Xへの投稿に失敗しました。")
            
    except Exception as e:
        logging.error("処理中にエラーが発生しました。", exc_info=True)
    finally:
        logging.info("処理を終了します。")

if __name__ == "__main__":
    main()
