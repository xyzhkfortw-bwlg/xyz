# ETF 財經日報機器人 — 自動化部署教學筆記

> 本文記錄完整的成功部署流程，以及過程中踩過的坑，供日後參考。

---

## ✅ 成功完成的事項

1. 建立 Telegram Bot 並取得 Chat ID
2. 建立 GitHub 私有 Repository
3. 上傳三個檔案（`etf_report.py`、`requirements.txt`、`.github/workflows/daily_etf_report.yml`）
4. 設定 GitHub Secrets（`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`）
5. 手動觸發 Workflow，33 秒內成功推播 ETF 日報到 Telegram

---

## 🐛 踩過的坑（避免重蹈覆轍）

### 錯誤 1：Telegram `/newbot` 輸入到搜尋欄
- **問題**：Telegram Web 預設焦點在搜尋欄，直接打字會變成搜尋
- **修正**：用 JavaScript 找到 `.input-message-input`（contenteditable div）再用 `document.execCommand('insertText', false, '/newbot')` 輸入，接著找 `.btn-send` 按鈕 `.click()` 送出

### 錯誤 2：Enter 鍵在 Telegram Web 產生換行，沒有送出訊息
- **問題**：`KeyboardEvent` dispatch keyCode 13 無效
- **修正**：直接找 `.btn-send` 按鈕呼叫 `.click()`，不要模擬鍵盤事件

### 錯誤 3：Telegram `getUpdates` API 回傳空陣列
- **問題**：透過 Telegram Web 傳給 Bot 的訊息不走 Bot API polling，所以 `getUpdates` 抓不到
- **修正**：從 Telegram Web 的 localStorage 取 Chat ID：
  ```javascript
  JSON.parse(localStorage.getItem('user_auth')).id
  // → 取得數字型 Chat ID（例如 8693540883）
  ```

### 錯誤 4：GitHub 空 Repo 無法用 `/upload/main` 上傳
- **問題**：空 Repository 沒有 `main` branch，`/upload/main` 會跳回首頁
- **修正**：改用 `/new/main` 建立第一個檔案，commit 後 `main` branch 才會存在

### 錯誤 5：GitHub PAT（Personal Access Token）需要 passkey 驗證
- **問題**：建立 PAT 需要生物辨識（passkey）或 sudo 模式，無法自動化
- **修正**：放棄 PAT 方式，改用 GitHub 網頁編輯器直接貼上程式碼

### 錯誤 6：GitHub CM6 編輯器無法用一般方式貼上內容
- **問題**：GitHub 現在用 CodeMirror 6（CM6），以下方法都失敗：
  - `CodeMirror.setValue()` → CM5 API，CM6 不支援
  - `navigator.clipboard.writeText()` + Ctrl+V → 系統剪貼簿內容不對
  - `document.execCommand('copy')` + Ctrl+V → 一直貼到舊的剪貼簿內容
- **✅ 成功方法**：用 `ClipboardEvent` 搭配 `DataTransfer`，直接 dispatch 到 `.cm-content` 元素：
  ```javascript
  const content = `你的程式碼內容`;
  const editor = document.querySelector('.cm-content');
  editor.focus();
  const dt = new DataTransfer();
  dt.setData('text/plain', content);
  const pasteEvent = new ClipboardEvent('paste', {
    clipboardData: dt,
    bubbles: true,
    cancelable: true
  });
  editor.dispatchEvent(pasteEvent);
  // dispatchEvent 回傳 false 是正常的（CM6 攔截處理），內容仍然會正確插入
  ```

### 錯誤 7：CM6 編輯器 dispatchEvent 回傳 false 讓人誤以為失敗
- **問題**：`dispatchEvent` 回傳 `false` 代表事件被 `preventDefault()`，不代表失敗
- **說明**：CM6 自己的 paste handler 接管了事件，`text/plain` 內容確實有被插入，需要用 `editor.innerText` 驗證確認

### 錯誤 8：建立 `.github/workflows/` 子目錄的方式
- **說明**：在 GitHub 新增檔案時，在檔名欄位輸入完整路徑（包含 `/`），GitHub 會自動建立目錄：
  ```
  檔名輸入：.github/workflows/daily_etf_report.yml
  ```
  輸入 `/` 後目錄會變成麵包屑，最後只剩檔名顯示在輸入框

### 錯誤 9：GitHub Secret 表單欄位的正確選取方式
- **問題**：`input[placeholder="Name"]` 等選取器找不到元素
- **✅ 成功方法**：
  ```javascript
  const nameInput = document.querySelector('#secret_name');
  const valueTextarea = document.querySelector('#secret_value');
  ```

### 錯誤 10：GitHub Actions「Run workflow」按鈕藏在 `<details>` 裡
- **問題**：直接找 `button` 找不到「Run workflow」
- **✅ 成功方法**：先點開 `<details>` 的 `<summary>`，再點 `<button>`：
  ```javascript
  // 第一步：展開 dropdown
  const details = Array.from(document.querySelectorAll('details'));
  const runDetails = details.find(d => d.textContent.includes('Run workflow'));
  runDetails.querySelector('summary').click();

  // 第二步：點執行按鈕
  const runBtn = Array.from(document.querySelectorAll('button'))
    .find(b => b.textContent.trim() === 'Run workflow');
  runBtn.click();
  ```

---

## 📄 完整程式碼

### `etf_report.py`（主程式）

```python
"""
ETF 財經日報機器人
監控 ETF：0050、0056、SPY、QQQ
每日自動計算 MA5/MA20/RSI 並推播至 Telegram
"""

import os
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone, timedelta

# ============================================================
# 設定區（在 GitHub Secrets 設定，不要直接填在這裡）
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# 監控的 ETF 清單
ETF_LIST = [
    {"symbol": "0050.TW", "name": "元大台灣50"},
    {"symbol": "0056.TW", "name": "元大高股息"},
    {"symbol": "SPY",     "name": "標普500 ETF"},
    {"symbol": "QQQ",     "name": "那斯達克100 ETF"},
]

# ============================================================
# 技術指標計算
# ============================================================

def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    """計算 RSI 相對強弱指數"""
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def get_etf_data(symbol: str) -> dict | None:
    """抓取 ETF 資料並計算技術指標"""
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period="60d")  # 抓 60 天，確保 MA20 夠數據

        if hist.empty or len(hist) < 20:
            print(f"[警告] {symbol} 資料不足，跳過")
            return None

        close    = hist["Close"]
        latest   = round(float(close.iloc[-1]), 2)
        prev     = round(float(close.iloc[-2]), 2)
        chg      = round(latest - prev, 2)
        chg_pct  = round((chg / prev) * 100, 2)

        ma5      = round(float(close.rolling(5).mean().iloc[-1]),  2)
        ma20     = round(float(close.rolling(20).mean().iloc[-1]), 2)
        rsi      = calculate_rsi(close)

        # 成交量（百萬）
        vol      = hist["Volume"].iloc[-1]
        vol_str  = f"{vol/1_000_000:.2f}M" if vol >= 1_000_000 else f"{vol:,}"

        # 判斷均線趨勢
        if latest > ma5 > ma20:
            trend = "⬆️ 多頭排列"
        elif latest < ma5 < ma20:
            trend = "⬇️ 空頭排列"
        elif latest > ma20:
            trend = "➡️ 站上月線"
        else:
            trend = "⚠️ 跌破月線"

        # RSI 判斷
        if rsi >= 70:
            rsi_label = "🔴 超買區"
        elif rsi <= 30:
            rsi_label = "🟢 超賣區"
        elif rsi >= 55:
            rsi_label = "偏多"
        elif rsi <= 45:
            rsi_label = "偏空"
        else:
            rsi_label = "中性"

        # 漲跌符號
        arrow = "📈" if chg >= 0 else "📉"
        sign  = "+" if chg >= 0 else ""

        return {
            "symbol":    symbol,
            "latest":    latest,
            "chg":       chg,
            "chg_pct":   chg_pct,
            "ma5":       ma5,
            "ma20":      ma20,
            "rsi":       rsi,
            "rsi_label": rsi_label,
            "trend":     trend,
            "vol":       vol_str,
            "arrow":     arrow,
            "sign":      sign,
        }

    except Exception as e:
        print(f"[錯誤] 抓取 {symbol} 失敗: {e}")
        return None


# ============================================================
# 組合日報訊息
# ============================================================

def build_report() -> str:
    tz_taipei = timezone(timedelta(hours=8))
    now       = datetime.now(tz_taipei)
    date_str  = now.strftime("%Y/%m/%d")
    weekday   = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]

    lines = [
        f"📊 *ETF 財經日報* — {date_str}（週{weekday}）",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for etf in ETF_LIST:
        data = get_etf_data(etf["symbol"])
        if data is None:
            lines.append(f"\n❓ *{etf['name']}* — 無法取得資料\n")
            continue

        block = (
            f"\n{data['arrow']} *{etf['name']}* `{etf['symbol']}`\n"
            f"  收盤價：{data['latest']}　"
            f"漲跌：{data['sign']}{data['chg']} ({data['sign']}{data['chg_pct']}%)\n"
            f"  MA5：{data['ma5']}　MA20：{data['ma20']}\n"
            f"  RSI(14)：{data['rsi']} — {data['rsi_label']}\n"
            f"  趨勢：{data['trend']}\n"
            f"  成交量：{data['vol']}\n"
        )
        lines.append(block)

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 _以上僅供參考，投資有風險，請自行判斷。_")

    return "\n".join(lines)


# ============================================================
# Telegram 推播
# ============================================================

def send_to_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[錯誤] 缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 環境變數")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "Markdown",
    }

    try:
        resp = requests.post(url, data=payload, timeout=15)
        if resp.status_code == 200:
            print("✅ Telegram 推播成功！")
            return True
        else:
            print(f"❌ Telegram 推播失敗：{resp.status_code} — {resp.text}")
            return False
    except requests.RequestException as e:
        print(f"❌ 網路錯誤：{e}")
        return False


# ============================================================
# 主程式
# ============================================================

def main():
    print("🚀 開始產生 ETF 日報...")
    report = build_report()
    print("\n===== 日報預覽 =====")
    print(report)
    print("====================\n")
    send_to_telegram(report)


if __name__ == "__main__":
    main()
```

---

### `requirements.txt`（套件清單）

```
yfinance>=0.2.40
pandas>=2.0.0
requests>=2.31.0
```

---

### `.github/workflows/daily_etf_report.yml`（排程設定）

```yaml
name: ETF 每日財經日報推播

on:
  # 每天台灣時間早上 8:00 執行 (UTC 00:00)
  schedule:
    - cron: "0 0 * * 1-5"   # 週一到週五

  # 允許手動從 GitHub 介面觸發（方便測試）
  workflow_dispatch:

jobs:
  send-etf-report:
    runs-on: ubuntu-latest

    steps:
      - name: 📥 Checkout 程式碼
        uses: actions/checkout@v4

      - name: 🐍 設定 Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: 📦 安裝相依套件
        run: pip install -r requirements.txt

      - name: 🚀 執行 ETF 日報推播
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID:   ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python etf_report.py
```

---

## 🔑 重要資訊備份

| 項目 | 值 |
|------|-----|
| GitHub Repository | `xyzhkfortw-bwlg/etf-telegram-bot`（私有） |
| Telegram Bot Token | 儲存在 GitHub Secret `TELEGRAM_BOT_TOKEN` |
| Telegram Chat ID | 儲存在 GitHub Secret `TELEGRAM_CHAT_ID` |
| 自動執行時間 | 週一～週五 台灣時間早上 8:00 |
| 監控 ETF | 0050.TW、0056.TW、SPY、QQQ |

---

## 📋 完整自動化流程摘要

```
1. Telegram Web（web.telegram.org）
   → 找 @BotFather → 傳 /newbot → 取得 Bot Token
   → 從 localStorage.user_auth.id 取得自己的 Chat ID

2. GitHub（github.com）
   → 新建 Private Repository
   → 用 ClipboardEvent 注入法上傳 etf_report.py
   → 上傳 requirements.txt
   → 上傳 .github/workflows/daily_etf_report.yml（路徑直接打在檔名欄）
   → Settings → Secrets → 新增 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID
   → Actions → ETF 每日財經日報推播 → Run workflow（手動測試）

3. 驗證
   → GitHub Actions 執行結果：Status: Success（33秒）
   → Telegram 收到 ETF 日報推播
```

---

## 💡 GitHub CM6 編輯器貼上技巧（核心知識）

這是最重要的技術突破。未來只要需要在 GitHub 網頁編輯器貼入程式碼，都用這個方法：

```javascript
function pasteToGitHubEditor(content) {
  const editor = document.querySelector('.cm-content');
  if (!editor) return console.error('找不到編輯器');
  
  editor.focus();
  
  const dt = new DataTransfer();
  dt.setData('text/plain', content);
  
  const pasteEvent = new ClipboardEvent('paste', {
    clipboardData: dt,
    bubbles: true,
    cancelable: true
  });
  
  editor.dispatchEvent(pasteEvent);
  
  // 驗證
  console.log('前100字：', editor.innerText.substring(0, 100));
}
```

> ⚠️ `dispatchEvent` 回傳 `false` 是正常現象，不代表失敗。請用 `editor.innerText` 確認內容有進去。

---

*最後更新：2026/04/24* 版權聲明
