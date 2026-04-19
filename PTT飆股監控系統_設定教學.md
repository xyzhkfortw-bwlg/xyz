# 🚀 PTT 飆股雷達監控系統 — 完整設定教學(建議使用VPN多跳幾個比較穩定)

> 本系統會自動巡邏 PTT 股版，抓取有價值的文章，透過 **Gemini AI** 進行語意分析，並同時推播到 **Slack** 和 **Telegram**，讓你第一時間掌握市場情緒。

---

## 📋 系統架構

```
PTT 股版 (https://www.ptt.cc/bbs/Stock)
        ↓  爬蟲抓取文章
Gemini AI 語意分析（提取股票代號、多空方向、熱度分數）
        ↓  熱度 ≥ 7 分時觸發推播
Slack + Telegram 雙平台通知
```

---

## 🛠️ 事前準備

### 需要的帳號與 API 金鑰

| 服務 | 用途 | 如何取得 |
|------|------|---------|
| **Google Gemini API** | AI 語意分析引擎 | [Google AI Studio](https://aistudio.google.com/) |
| **Slack Webhook URL** | 接收推播通知 | Slack 後台 → Apps → Incoming Webhooks |
| **Telegram Bot Token** | 接收推播通知 | 在 Telegram 找 @BotFather 建立機器人 |
| **Telegram Chat ID** | 指定推播對象 | 找 @userinfobot 取得自己的 Chat ID |

---

## ⚙️ 安裝步驟

### 第一步：確認 Python 環境

```bash
python --version
# 需要 Python 3.8 以上
```

### 第二步：安裝所需套件

```bash
pip install requests beautifulsoup4 google-generativeai
```

### 第三步：下載程式檔案

確認資料夾內有以下三個檔案：

```
ptt-飆股監控/
├── ptt_crawler.py    ← 主程式（爬蟲 + AI 分析 + 推播）
├── test_ai.py        ← 測試 Gemini AI 連線是否正常
└── run_ptt.bat       ← Windows 一鍵執行腳本
```

---

## 🔑 設定 API 金鑰

打開 `ptt_crawler.py`，找到最上方的設定區塊，填入你的金鑰：

```python
# ==========================================
# 🛑 第 1 步：填寫你的所有金鑰
# ==========================================
GEMINI_API_KEY = "你的_Gemini_API_Key"
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/你的_Webhook_URL"

# Telegram 資訊
TG_TOKEN = "你的_Telegram_Bot_Token"
TG_CHAT_ID = "你的_Telegram_Chat_ID"
```

---

## 🧪 測試連線

### 測試 Gemini AI 是否正常

執行 `test_ai.py`，確認能列出可用模型：

```bash
python test_ai.py
```

✅ 成功輸出範例：
```
正在連線 Google 伺服器，查詢可用的模型清單...

✅ 發現可用模型： models/gemini-2.5-flash
✅ 發現可用模型： models/gemini-1.5-pro
...
```

❌ 如果出現錯誤，請確認：
- API Key 是否填寫正確
- 網路是否可以連到 Google 服務

---

## ▶️ 執行系統

### 方法一：直接執行 Python（推薦）

```bash
python ptt_crawler.py
```

### 方法二：Windows 雙擊 BAT 檔

直接雙擊 `run_ptt.bat`，會自動切換到正確目錄並執行程式。

> ⚠️ **注意**：請先確認 `run_ptt.bat` 裡的路徑與你實際的資料夾位置相符：
> ```bat
> cd /d "C:\ClaudeBot\ptt-飆股監控"
> ```

---

## 📊 執行流程說明

程式啟動後，會依照以下流程運作：

1. **巡邏 5 頁** PTT 股版（可在程式碼調整 `pages_to_scan` 數值）
2. **篩選文章**：只處理標題含有以下標籤的文章：
   - `[標的]`
   - `[情報]`
   - `[心得]`
   - `[分析]`
3. **AI 分析**：送入 Gemini，取得以下資訊：
   - 股票名稱 / 代號
   - 多空方向（多頭 / 空頭）
   - 熱度分數（1～10）
   - 一句話摘要
4. **觸發條件**：**熱度分數 ≥ 7** 才推播
5. **同步推播** 到 Slack 和 Telegram

---

## 📱 推播訊息格式

```
🚨 【PTT 潛力股雷達】

📈 標的：台積電 (2330)
🔥 熱度：9 / 10
📊 方向：多頭

💬 分析：法人大量買超，外資看好下季財報優於預期

🔗 查看 PTT 原文 → https://www.ptt.cc/...
```

---

## 📝 完整原始碼

### `ptt_crawler.py` — 主程式

```python
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import time

# ==========================================
# 🛑 第 1 步：填寫你的所有金鑰
# ==========================================
GEMINI_API_KEY = "你的_Gemini_API_Key"
SLACK_WEBHOOK_URL = "你的_Slack_Webhook_URL"

# Telegram 資訊
TG_TOKEN = "你的_Telegram_Bot_Token"
TG_CHAT_ID = "你的_Telegram_Chat_ID"

# 初始化 Gemini AI 模型
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-2.5-flash')

# ==========================================
# 🛠️ 第 2 步：核心功能函式
# ==========================================

def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cookie": "over18=1"
    }

def fetch_article_content(article_url):
    """抓取單篇 PTT 文章內容"""
    try:
        response = requests.get(article_url, headers=get_headers(), timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            main_content = soup.find(id="main-content")
            if main_content:
                return main_content.text
    except:
        pass
    return ""

def analyze_with_ai(content):
    """送入 Gemini 分析，回傳結構化 JSON 結果"""
    if not content:
        return None
    prompt = (
        f"你是一個專業股市分析師。請分析以下 PTT 內容，提取關鍵資訊。\n"
        f"內容：{content[:1500]}\n"
        f"請嚴格遵守 JSON 格式輸出：{{'stock': '名稱', 'sentiment': '多空', 'score': 8, 'summary': '一句話總結'}}"
    )
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_text)
    except:
        return None

def send_to_slack(data, url):
    """發送推播通知到 Slack"""
    message = (
        f"🚨 *【PTT 潛力股雷達】*\n"
        f"📈 *標的：* {data['stock']}\n"
        f"🔥 *熱度：* {data['score']}/10\n"
        f"📊 *方向：* {data['sentiment']}\n"
        f"💬 *分析：* {data['summary']}\n"
        f"🔗 {url}"
    )
    payload = {"text": message}
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        print("✅ Slack 發送成功")
    except:
        print("⚠️ Slack 發送失敗")

def send_to_telegram(data, url):
    """發送推播通知到 Telegram"""
    message = (
        f"🚨 *【PTT 潛力股雷達】*\n\n"
        f"📈 *標的：* {data['stock']}\n"
        f"🔥 *熱度：* {data['score']} / 10\n"
        f"📊 *方向：* {data['sentiment']}\n\n"
        f"💬 *分析：* {data['summary']}\n\n"
        f"🔗 [查看 PTT 原文]({url})"
    )
    api_url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(api_url, data=payload, timeout=10)
        print("✅ Telegram 發送成功")
    except:
        print("⚠️ Telegram 發送失敗")

# ==========================================
# 🚀 第 3 步：執行邏輯
# ==========================================

def main():
    base_url = "https://www.ptt.cc/bbs/Stock/index.html"
    current_url = base_url
    pages_to_scan = 5  # 要巡邏的頁數，可自行調整

    print(f"啟動 PTT 雙平台監控雷達 (範圍：{pages_to_scan} 頁)...\n")

    try:
        for page in range(pages_to_scan):
            print(f"📄 正在巡邏第 {page + 1} 頁...")
            response = requests.get(current_url, headers=get_headers(), timeout=10)
            if response.status_code != 200:
                break

            soup = BeautifulSoup(response.text, "html.parser")

            # 取得「上一頁」連結，準備翻頁
            btns = soup.find_all("a", class_="btn wide")
            for btn in btns:
                if "上頁" in btn.text:
                    current_url = "https://www.ptt.cc" + btn["href"]
                    break

            # 遍歷所有文章
            articles = soup.find_all("div", class_="r-ent")
            for article in articles:
                title_tag = article.find("div", class_="title").find("a")
                if title_tag:
                    title = title_tag.text
                    link = "https://www.ptt.cc" + title_tag["href"]

                    # 只處理有意義的文章標籤
                    if any(tag in title for tag in ["[標的]", "[情報]", "[心得]", "[分析]"]):
                        print(f"📌 處理中：{title}")
                        content = fetch_article_content(link)
                        ai_result = analyze_with_ai(content)

                        if ai_result:
                            score = int(ai_result.get('score', 0))
                            if score >= 7:  # 熱度門檻，可調整
                                print(f"📲 觸發推播！AI 分數：{score}")
                                send_to_slack(ai_result, link)
                                send_to_telegram(ai_result, link)

                        time.sleep(8)  # 避免對 PTT 造成過大請求壓力

            time.sleep(3)  # 翻頁間隔

    except Exception as e:
        print(f"❌ 錯誤：{e}")


if __name__ == "__main__":
    main()
```

---

### `test_ai.py` — 測試 Gemini 連線

```python
import google.generativeai as genai

# ⚠️ 請填入你的 API Key
YOUR_API_KEY = "你的_Gemini_API_Key"

genai.configure(api_key=YOUR_API_KEY)

print("正在連線 Google 伺服器，查詢可用的模型清單...\n")

try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ 發現可用模型： {m.name}")
except Exception as e:
    print(f"❌ 查詢失敗，錯誤訊息：{e}")
```

---

### `run_ptt.bat` — Windows 一鍵執行腳本

```bat
@echo off
cd /d "C:\ClaudeBot\ptt-飆股監控"
python ptt_crawler.py
pause
```

> ⚠️ 請把路徑改成你實際的資料夾位置。

---

## ❓ 常見問題排解

| 問題 | 可能原因 | 解決方法 |
|------|---------|---------|
| `ModuleNotFoundError` | 套件未安裝 | 執行 `pip install requests beautifulsoup4 google-generativeai` |
| Gemini API 連線失敗 | API Key 錯誤或網路問題 | 先執行 `test_ai.py` 確認 |
| PTT 抓不到資料 | IP 被 PTT 暫時封鎖 | 等待幾分鐘後重試，或調整 `time.sleep()` 間隔 |
| Slack / Telegram 沒收到通知 | Webhook URL 或 Token 填錯 | 再次確認金鑰，並確認熱度分數 ≥ 7 才會推播 |
| BAT 檔案閃退 | 路徑不對 | 確認 `run_ptt.bat` 內的路徑與實際位置相符 |

---

## 🔧 進階調整

### 調整巡邏頁數
```python
pages_to_scan = 5  # 改成 10 就會巡邏更多頁
```

### 調整推播門檻
```python
if score >= 7:  # 改成 8 或 9 可以減少推播頻率
```

### 新增文章標籤篩選
```python
if any(tag in title for tag in ["[標的]", "[情報]", "[心得]", "[分析]", "[請益]"]):
```

---

## ✅ 設定完成確認清單

- [ ] Python 3.8+ 已安裝
- [ ] 套件已安裝（requests, beautifulsoup4, google-generativeai）
- [ ] Gemini API Key 已填入 `ptt_crawler.py`
- [ ] Slack Webhook URL 已填入 `ptt_crawler.py`
- [ ] Telegram Bot Token 和 Chat ID 已填入 `ptt_crawler.py`
- [ ] `test_ai.py` 測試成功，能列出可用模型
- [ ] `run_ptt.bat` 路徑已更新為實際路徑
- [ ] 執行 `ptt_crawler.py`，確認有看到「📄 正在巡邏第 1 頁...」

---

*系統建置完成後，建議使用 Windows 工作排程器或 Linux cron job 設定每1小時或是1天自動執行一次。*
