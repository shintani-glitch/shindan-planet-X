import os
import random
import json
import gspread
import tweepy
import google.generativeai as genai
import logging

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_gspread_client():
    """Googleスプレッドシートに接続"""
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not creds_json:
        logging.error("環境変数 'GOOGLE_SERVICE_ACCOUNT_JSON' が見つかりません。")
        raise ValueError("GoogleサービスアカウントのJSON認証情報が設定されていません。")
    
    creds_dict = json.loads(creds_json)
    client = gspread.service_account_from_dict(creds_dict)
    return client

def get_spreadsheet_data(spreadsheet):
    """スプレッドシートから記事リストと前回投稿URLを取得"""
    # 全記事リストを取得
    articles_sheet = spreadsheet.worksheet("articles")
    all_articles = articles_sheet.get_all_records()
    all_urls = [article['url'] for article in all_articles]
    
    # 前回投稿URLを取得
    log_sheet = spreadsheet.worksheet("log")
    last_tweeted_url = log_sheet.acell('A2').value
    
    return all_urls, last_tweeted_url, log_sheet

def generate_tweet_text(article_url):
    """Gemini APIでツイート文を生成"""
    # (この関数の内容は前回の回答と同じなので省略)
    # ...

def post_to_x(text):
    """X (Twitter) API v2 でツイート"""
    # (この関数の内容は前回の回答と同じなので省略)
    # ...

def main():
    """メイン処理"""
    logging.info("ツイート自動投稿処理を開始します。")
    
    try:
        spreadsheet_name = os.environ.get('SPREADSHEET_NAME')
        if not spreadsheet_name:
            raise ValueError("環境変数 'SPREADSHEET_NAME' が設定されていません。")

        # 1. スプレッドシートに接続しデータを取得
        client = setup_gspread_client()
        spreadsheet = client.open(spreadsheet_name)
        all_urls, last_tweeted_url, log_sheet = get_spreadsheet_data(spreadsheet)
        
        if not all_urls:
            logging.warning("スプレッドシートに投稿対象の記事がありません。")
            return

        logging.info(f"全記事数: {len(all_urls)}件, 前回投稿URL: {last_tweeted_url}")

        # 2. 抽選候補リストを作成（前回投稿したものを除外）
        candidate_urls = [url for url in all_urls if url != last_tweeted_url]
        
        # もし候補リストが空になった場合（記事が1つしかない場合など）、
        # 全リストを候補に戻すことで連続投稿を許容する
        if not candidate_urls:
            candidate_urls = all_urls
            logging.warning("抽選候補が0件でした。全記事を対象に再抽選します。")

        # 3. 候補からランダムに1つ選ぶ
        selected_url = random.choice(candidate_urls)
        logging.info(f"今回投稿するURLを選びました: {selected_url}")

        # 4. Geminiで投稿文を生成
        tweet_text = generate_tweet_text(selected_url)
        if not tweet_text:
            raise RuntimeError("Gemini APIによる投稿文の生成に失敗しました。")
        logging.info("投稿文を生成しました。")

        # 5. Xに投稿
        is_success = post_to_x(tweet_text)
        
        # 6. 成功した場合、ログシートを更新
        if is_success:
            log_sheet.update('A2', selected_url)
            logging.info(f"ログシートを更新しました。新しい最終投稿URL: {selected_url}")
        else:
            raise RuntimeError("Xへの投稿に失敗しました。")
            
    except Exception as e:
        logging.error("処理中にエラーが発生しました。", exc_info=True)
    finally:
        logging.info("ツイート自動投稿処理を終了します。")

# --- 以下に generate_tweet_text と post_to_x 関数を記述 ---

def generate_tweet_text(article_url):
    """Gemini APIを使用してツイート文を生成"""
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    if not gemini_api_key:
        raise ValueError("環境変数 'GEMINI_API_KEY' が設定されていません。")
    
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-pro')

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
    """X (Twitter) API v2 を使ってツイートを投稿"""
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

if __name__ == "__main__":
    main()
