# YouTube AI 留言自動回覆機器人 — 完整教學

> **頻道：** BWLG  
> **技術：** Python + OpenAI GPT-4o-mini + YouTube Data API v3 + GitHub Actions + Telegram  
> **GitHub Repo：** `xyzhkfortw-bwlg/youtube-ai-bot`（私人）

---

## 目錄

1. [專案簡介](#1-專案簡介)
2. [專案架構](#2-專案架構)
3. [事前準備（API 金鑰）](#3-事前準備api-金鑰)
4. [程式碼說明](#4-程式碼說明)
   - [bot.py（主程式）](#botpy主程式)
   - [get_refresh_token.py（取得 OAuth Token）](#get_refresh_tokenpy取得-oauth-token)
   - [requirements.txt（套件清單）](#requirementstxt套件清單)
   - [.gitignore（安全設定）](#gitignore安全設定)
   - [replied_ids.json（防重複紀錄）](#replied_idsjson防重複紀錄)
   - [youtube_bot.yml（GitHub Actions 排程）](#youtube_botymlgithub-actions-排程)
5. [設定 GitHub Secrets](#5-設定-github-secrets)
6. [本機取得 YouTube Refresh Token](#6-本機取得-youtube-refresh-token)
7. [手動觸發測試](#7-手動觸發測試)
8. [常見問題排解](#8-常見問題排解)

---

## 1. 專案簡介

這個機器人會自動：

- 每 **3 小時**掃描 BWLG 頻道最新的 5 部影片
- 讀取每部影片的新留言（最多 30 則）
- 用 **OpenAI GPT-4o-mini** 生成符合 BWLG 頻道風格的繁體中文回覆
- 透過 **YouTube Data API** 自動發布回覆
- 用 **Telegram Bot** 發送通知（成功幾則、跳過幾則）
- 將已回覆的留言 ID 記錄在 `replied_ids.json`，**防止重複回覆**

---

## 2. 專案架構

```
youtube-ai-bot/
├── .github/
│   └── workflows/
│       └── youtube_bot.yml    # GitHub Actions 自動排程
├── bot.py                     # 主程式
├── get_refresh_token.py       # 本機取得 OAuth Token（只用一次）
├── requirements.txt           # Python 套件清單
├── replied_ids.json           # 已回覆留言 ID 紀錄
└── .gitignore                 # 排除敏感檔案
```

---

## 3. 事前準備（API 金鑰）

你需要準備以下 6 個金鑰：

| 金鑰名稱 | 取得方式 |
|---------|---------|
| `YOUTUBE_CLIENT_ID` | Google Cloud Console → OAuth 2.0 用戶端 |
| `YOUTUBE_CLIENT_SECRET` | 同上 |
| `YOUTUBE_REFRESH_TOKEN` | 執行 `get_refresh_token.py` 取得 |
| `OPENAI_API_KEY` | platform.openai.com |
| `TELEGRAM_BOT_TOKEN` | Telegram BotFather |
| `TELEGRAM_CHAT_ID` | 傳訊給 Bot 後查詢 |

### 3.1 建立 Google Cloud 專案

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立新專案（例如 `bwlg-youtube-bot`）
3. 啟用 **YouTube Data API v3**
4. 建立 **OAuth 2.0 用戶端 ID**（類型選「桌面應用程式」）
5. 下載 `client_secret.json`（本機使用，**不要上傳 GitHub**）

### 3.2 建立 Telegram Bot

1. 在 Telegram 搜尋 `@BotFather`
2. 發送 `/newbot` 建立機器人，取得 `TELEGRAM_BOT_TOKEN`
3. 傳任意訊息給你的 Bot
4. 前往 `https://api.telegram.org/bot<TOKEN>/getUpdates` 取得 `TELEGRAM_CHAT_ID`

---

## 4. 程式碼說明

### bot.py（主程式）

```python
"""
YouTube AI 留言自動回覆機器人
使用 OpenAI GPT 生成回覆，並透過 Telegram 發送通知
"""

import os
import json
import datetime
import requests
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# ── 環境變數 ──────────────────────────────────────────────
YOUTUBE_CLIENT_ID     = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
YOUTUBE_REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]
OPENAI_API_KEY        = os.environ["OPENAI_API_KEY"]
TELEGRAM_BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── BWLG 頻道設定 ─────────────────────────────────────────
CHANNEL_ID = "UCxxxxxxxxxxxxxxxxxx"  # 替換為實際頻道 ID
REPLIED_IDS_FILE = "replied_ids.json"
MAX_VIDEOS = 5
MAX_COMMENTS = 30

# ── BWLG AI 人設（System Prompt）────────────────────────────
SYSTEM_PROMPT = """你是 BWLG 頻道的 AI 助理，負責回覆 YouTube 留言。

【回覆風格】
- 使用繁體中文
- 語氣友善、活潑，帶有 BWLG 的個性
- 回覆簡短有力（50字以內）
- 對問題給予真誠回應，對讚美表達感謝
- 不回覆廣告、垃圾訊息或惡意留言

【注意事項】
- 若留言是廣告或無意義內容，回覆「SKIP」
- 保持正向積極的態度
- 可以加入適當的 emoji
"""


def get_youtube_client():
    """建立已認證的 YouTube API 客戶端"""
    creds = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"]
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def load_replied_ids() -> set:
    """載入已回覆的留言 ID"""
    if os.path.exists(REPLIED_IDS_FILE):
        with open(REPLIED_IDS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_replied_ids(replied_ids: set):
    """儲存已回覆的留言 ID"""
    with open(REPLIED_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(replied_ids), f, ensure_ascii=False, indent=2)


def get_recent_videos(youtube, channel_id: str, max_results: int = 5) -> list:
    """取得頻道最新影片"""
    response = youtube.search().list(
        part="snippet",
        channelId=channel_id,
        order="date",
        type="video",
        maxResults=max_results
    ).execute()

    videos = []
    for item in response.get("items", []):
        videos.append({
            "id":    item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "url":   f"https://www.youtube.com/watch?v={item['id']['videoId']}"
        })
    print(f"找到 {len(videos)} 部最新影片")
    return videos


def get_top_level_comments(youtube, video_id: str, max_results: int = 30) -> list:
    """取得影片的頂層留言"""
    try:
        response = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=max_results,
            order="time",
        ).execute()

        comments = []
        for item in response.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "id":     item["id"],
                "text":   snippet["textDisplay"],
                "author": snippet["authorDisplayName"],
            })
        return comments
    except Exception as e:
        print(f"  取得留言失敗：{e}")
        return []


def generate_reply(comment_text: str) -> str:
    """呼叫 OpenAI GPT-4o-mini 生成回覆"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"留言內容：{comment_text}"}
        ],
        "max_tokens": 150,
        "temperature": 0.8
    }
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def post_reply(youtube, comment_id: str, reply_text: str):
    """在 YouTube 發布回覆"""
    youtube.comments().insert(
        part="snippet",
        body={
            "snippet": {
                "parentId": comment_id,
                "textOriginal": reply_text
            }
        }
    ).execute()


def send_telegram(message: str):
    """傳送 Telegram 通知"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        print(f"Telegram 通知失敗：{e}")


def main():
    print("=" * 50)
    print(f"YouTube AI 機器人啟動 — {datetime.datetime.now()}")
    print("=" * 50)

    youtube = get_youtube_client()
    replied_ids = load_replied_ids()

    replied_count = 0
    skipped_count = 0

    videos = get_recent_videos(youtube, CHANNEL_ID, MAX_VIDEOS)

    for video in videos:
        print(f"\n影片：{video['title']}")
        comments = get_top_level_comments(youtube, video["id"], MAX_COMMENTS)

        for comment in comments:
            cid = comment["id"]

            if cid in replied_ids:
                skipped_count += 1
                continue

            print(f"  留言：{comment['text'][:50]}...")

            try:
                reply = generate_reply(comment["text"])

                if reply.strip().upper() == "SKIP":
                    print(f"  → GPT 判斷跳過")
                    skipped_count += 1
                    replied_ids.add(cid)
                    continue

                post_reply(youtube, cid, reply)
                replied_ids.add(cid)
                replied_count += 1
                print(f"  → 已回覆：{reply[:50]}")

            except Exception as e:
                print(f"  → 錯誤：{e}")
                skipped_count += 1

    save_replied_ids(replied_ids)

    summary = (
        f"YouTube AI 機器人執行完畢\n"
        f"已回覆：{replied_count} 則\n"
        f"跳過：{skipped_count} 則\n"
        f"時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    print("\n" + summary)
    send_telegram(summary)


if __name__ == "__main__":
    main()
```

> **重要：** 請將第 25 行的 `CHANNEL_ID = "UCxxxxxxxxxxxxxxxxxx"` 替換成你的 BWLG 頻道 ID。  
> 頻道 ID 可在 YouTube Studio → 設定 → 頻道 → 進階設定 中找到。

---

### get_refresh_token.py（取得 OAuth Token）

> 這個工具只需要在**本機執行一次**，用來取得 YouTube 的 Refresh Token。

```python
"""
本機執行工具：取得 YouTube OAuth Refresh Token
只需執行一次，取得 Refresh Token 後就可以上傳到 GitHub Secrets
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
CLIENT_SECRET_FILE = "client_secret.json"

def main():
    print("=" * 60)
    print("YouTube OAuth 授權工具")
    print("=" * 60)
    print()
    print("即將開啟瀏覽器進行 Google 登入授權...")
    print("請選擇你的 YouTube 頻道帳號並同意所有授權。")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES
    )

    creds = flow.run_local_server(port=8080, prompt="consent")

    print()
    print("=" * 60)
    print("授權成功！請複製以下三個值到 GitHub Secrets：")
    print("=" * 60)
    print()
    print("【YOUTUBE_CLIENT_ID】")
    print(f"  {creds.client_id}")
    print()
    print("【YOUTUBE_CLIENT_SECRET】")
    print(f"  {creds.client_secret}")
    print()
    print("【YOUTUBE_REFRESH_TOKEN】")
    print(f"  {creds.refresh_token}")
    print()
    print("=" * 60)

    token_data = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token
    }
    with open("youtube_tokens.json", "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2, ensure_ascii=False)
    print("備份已儲存到 youtube_tokens.json（此檔案不會上傳到 GitHub）")

if __name__ == "__main__":
    main()
```

**執行方式：**
```bash
# 先安裝套件
pip install google-auth-oauthlib

# 確保 client_secret.json 在同一個資料夾
python get_refresh_token.py
```

---

### requirements.txt（套件清單）

```
google-api-python-client==2.127.0
google-auth==2.29.0
google-auth-httplib2==0.2.0
google-auth-oauthlib==1.2.0
requests==2.31.0
```

---

### .gitignore（安全設定）

```gitignore
# 絕對不能上傳到 GitHub 的敏感檔案
client_secret.json
youtube_tokens.json
token.pickle
*.env
.env

# Python 暫存檔
__pycache__/
*.pyc
*.pyo
.pytest_cache/
venv/
.venv/
```

---

### replied_ids.json（防重複紀錄）

初始內容為空陣列，機器人每次執行後會自動更新此檔案：

```json
[]
```

---

### youtube_bot.yml（GitHub Actions 排程）

```yaml
name: YouTube AI Comment Assistant

on:
  schedule:
    - cron: '0 */3 * * *'   # 每 3 小時執行一次
  workflow_dispatch:         # 允許手動觸發

jobs:
  reply-comments:
    runs-on: ubuntu-latest
    concurrency:
      group: youtube-bot
      cancel-in-progress: false
    permissions:
      contents: write
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run YouTube AI Assistant
        env:
          YOUTUBE_CLIENT_ID: ${{ secrets.YOUTUBE_CLIENT_ID }}
          YOUTUBE_CLIENT_SECRET: ${{ secrets.YOUTUBE_CLIENT_SECRET }}
          YOUTUBE_REFRESH_TOKEN: ${{ secrets.YOUTUBE_REFRESH_TOKEN }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python bot.py

      - name: Commit updated replied IDs
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add replied_ids.json
          git diff --staged --quiet || git commit -m "chore: update replied_ids.json [skip ci]"
          git push
```

---

## 5. 設定 GitHub Secrets

1. 前往 GitHub Repo → **Settings** → **Secrets and variables** → **Actions**
2. 點擊 **New repository secret**，依序新增以下 6 個 Secret：

| Secret 名稱 | 說明 |
|------------|------|
| `YOUTUBE_CLIENT_ID` | Google OAuth 用戶端 ID |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth 用戶端密碼 |
| `YOUTUBE_REFRESH_TOKEN` | 執行 `get_refresh_token.py` 後取得 |
| `OPENAI_API_KEY` | OpenAI API 金鑰（`sk-...`）|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | 你的 Telegram Chat ID |

---

## 6. 本機取得 YouTube Refresh Token

**步驟：**

1. 從 Google Cloud Console 下載 `client_secret.json`，放到專案資料夾
2. 執行授權工具：
   ```bash
   python get_refresh_token.py
   ```
3. 瀏覽器會自動開啟 Google 登入頁面
4. 選擇 BWLG 頻道帳號，同意所有授權
5. 授權成功後，終端機會顯示三個值：
   - `YOUTUBE_CLIENT_ID`
   - `YOUTUBE_CLIENT_SECRET`
   - `YOUTUBE_REFRESH_TOKEN`
6. 將這三個值填入 GitHub Secrets

---

## 7. 手動觸發測試

所有 Secrets 設定完成後：

1. 前往 GitHub Repo → **Actions**
2. 點擊左側 **YouTube AI Comment Assistant**
3. 點擊右側 **Run workflow** → **Run workflow**
4. 等待約 30 秒，確認執行結果
5. 成功後你的 Telegram 會收到通知

---

## 8. 常見問題排解

### ❌ SyntaxError: unicode error

**原因：** `bot.py` 中的 emoji 前面多了 `\u`  
**解決：** 用 VS Code 的 Find & Replace（Regex 模式），搜尋 `\\u([^\da-fA-F\n])` 取代為 `$1`

---

### ❌ quotaExceeded

**原因：** YouTube Data API 每日配額用盡（預設 10,000 單位）  
**解決：** 減少 `MAX_VIDEOS` 或 `MAX_COMMENTS` 的數量，或等隔天重置

---

### ❌ invalid_grant

**原因：** Refresh Token 失效  
**解決：** 重新執行 `get_refresh_token.py` 取得新的 Token，更新 GitHub Secret

---

### ❌ GitHub Actions 排程沒有觸發

**原因：** GitHub 的免費帳號 Repo 若 60 天沒有活動，排程會暫停  
**解決：** 手動觸發一次 workflow，或定期 push commit 保持活躍

---

## 版本紀錄

| 日期 | 版本 | 說明 |
|------|------|------|
| 2026-04-26 | v1.0 | 初始版本，所有基礎功能完成 |

---

*由 Claude AI 協助建立*
