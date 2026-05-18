# 台股及 ETF 分析通知系統教學（含完整程式碼版）

> **對應檔案**：`台股及ETF分析通知系統.json`  
> **適用版本**：n8n v1.x（Self-hosted）、Claude API（claude-sonnet-4-6）、Telegram Bot  
> **最後更新**：2026-05-19

---

## 目錄

1. [系統功能總覽](#1-系統功能總覽)
2. [雙流程架構說明](#2-雙流程架構說明)
3. [前置準備](#3-前置準備)
4. [匯入工作流程](#4-匯入工作流程)
5. [Credentials 三組設定](#5-credentials-三組設定)
6. [Google Sheets 監控清單設定](#6-google-sheets-監控清單設定)
7. [流程 A：每日定時分析（逐節點完整說明）](#7-流程-a每日定時分析逐節點完整說明)
8. [流程 B：Telegram 即時指令查詢（逐節點完整說明）](#8-流程-btelegram-即時指令查詢逐節點完整說明)
9. [Telegram Bot 指令手冊](#9-telegram-bot-指令手冊)
10. [Telegram 通知訊息範例](#10-telegram-通知訊息範例)
11. [本機檔案說明](#11-本機檔案說明)
12. [常見問題與排除](#12-常見問題與排除)
13. [進階設定建議](#13-進階設定建議)
14. [重要免責聲明](#14-重要免責聲明)

---

## 1. 系統功能總覽

整合五大服務，提供兩種操作模式：

| 服務 | 用途 |
|------|------|
| **Google Sheets** | 雲端儲存定時監控清單，隨時在試算表新增/刪除標的 |
| **Yahoo Finance API** | 免費取得台股/ETF 日K線原始資料（近3個月） |
| **Claude API（Anthropic）** | AI 技術分析，輸出結構化買賣建議 JSON |
| **QuickChart.io** | 動態生成近5日收盤價折線圖（無需 API Key） |
| **Telegram Bot** | 推播分析報告、接收指令、回傳 K 線圖 |

**兩種使用方式：**
- **定時模式**：每個交易日 16:00（台北時間）自動分析 Google Sheets 清單，推播完整報告
- **即時查詢模式**：在 Telegram 輸入股票代碼（例如 `2330`），Bot 約 10~15 秒後回傳 AI 分析 + K 線圖

---

## 2. 雙流程架構說明

同一個 Workflow JSON 內包含兩條獨立的流程，並行運作：

```
【流程 A — 每日定時分析】

  每日收盤後觸發 (16:00 台北時間，週一至週五)
       │
       ▼
  Get row(s) in sheet  ← 從 Google Sheets 讀監控清單
       │
       ▼
  取得Yahoo Finance資料  ← 每個標的取近3個月日K線（可重試）
       │
       ▼
  計算技術指標  ← SMA/EMA/MACD/RSI14/量比/均線排列
       │
       ▼
  彙整所有標的資料  ← Aggregate 合併為 allData 陣列
       │
       ▼
  組建Claude分析提示詞  ← 格式化指標 + 組裝 API Request Body
       │
  ┌────┴────┐
  skipClaude?  (IF 節點)
  false ↓      true ↓（全部取得失敗）
  呼叫Claude    格式化全部失敗通知
  API分析            │
     │               │
  解析並格式化訊息    │
     └──────┬─────────┘
            ▼
     Telegram發送通知（單則合併報告）


【流程 B — Telegram 即時指令查詢】

  每30秒輪詢
       │
       ▼
  處理 Telegram 指令  ← getUpdates 讀訊息、處理 /list /add 等指令
       │
  trigger_ai? (IF 節點)
  true ↓（使用者輸入股票代碼）    false（管理指令）→ 結束
       │
  取得Yahoo Finance資料1
       │
  計算技術指標1
       │
  彙整所有標的資料1
       │
  組建Claude分析提示詞1  ← 含防呆：讓 Claude 自動補股票中文名稱
       │
  是否需要Claude分析1
  true ↓
  呼叫Claude API分析1
       │
  抓取即時K線圖  ← 取近5日收盤價供圖表使用
       │
  解析並格式化訊息1
       │
  Telegram發送通知1 ← sendPhoto：K線折線圖 + AI 分析說明文字
```

---

## 3. 前置準備

### 3-1. n8n 安裝

```bash
# Docker（推薦，自動設定時區）
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  -e GENERIC_TIMEZONE="Asia/Taipei" \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n

# 或 npm 安裝
npm install n8n -g && n8n start
```

開啟 `http://localhost:5678`

> ⚠️ **Windows 本機運行**：「處理 Telegram 指令」節點會在 `C:\ClaudeBot\` 建立本機檔案，n8n 需有該路徑的寫入權限。

### 3-2. 取得 Claude API Key

1. 前往 [https://console.anthropic.com](https://console.anthropic.com) → **API Keys** → **Create Key**
2. 複製金鑰（格式：`sk-ant-api03-...`）

### 3-3. 建立 Telegram Bot

1. 搜尋 `@BotFather` → `/newbot` → 取得 **Bot Token**（格式：`123456789:ABCdef...`）
2. 搜尋 `@userinfobot` → 取得你的 **Chat ID**（純數字）
3. 搜尋你的 Bot 帳號並傳一則任意訊息啟動對話

---

## 4. 匯入工作流程

1. n8n 左側 → **Workflows** → 右上 **⋮** → **Import from File**
2. 選擇 `台股及ETF分析通知系統.json` → **Import**
3. 先完成第 5、6 節的設定再開啟 Active 開關

---

## 5. Credentials 三組設定

### 5-1. Claude API — HTTP Custom Auth

節點「呼叫Claude API分析」與「呼叫Claude API分析1」均使用此 Credential。

**建立步驟：**

n8n → **Credentials** → **+ New** → 搜尋 **HTTP Custom Auth**

```
名稱：Custom Auth account

Headers 填入兩筆：
┌─────────────────────┬──────────────────────────────────┐
│ Name                │ Value                            │
├─────────────────────┼──────────────────────────────────┤
│ x-api-key           │ YOUR_CLAUDE_API_KEY_HERE         │
│ anthropic-version   │ 2023-06-01                       │
└─────────────────────┴──────────────────────────────────┘
```

儲存後，回到兩個「呼叫Claude API分析」節點，Credential 欄位選擇此組。

### 5-2. Google Sheets — OAuth2

n8n → **Credentials** → **+ New** → 搜尋 **Google Sheets OAuth2 API**  
依指示完成 Google 帳號授權，命名為 `Google Sheets account`。

### 5-3. Telegram Bot

n8n → **Credentials** → **+ New** → 搜尋 **Telegram API**

```
名稱：我的專屬台股小幫手Telegram
Access Token：（@BotFather 給的 Bot Token）
```

兩個「Telegram發送通知」節點均選擇此組。

---

## 6. Google Sheets 監控清單設定

### 6-1. 建立試算表格式

新增 Google Sheets，試算表命名為 `台股 AI 監控清單`。  
**第一列**填標題，**第二列起**填標的：

| A（ticker） | B（name） | C（type） |
|-------------|-----------|-----------|
| 2330.TW | 台積電 | stock |
| 2454.TW | 聯發科 | stock |
| 2303.TW | 聯電 | stock |
| 0050.TW | 元大台灣50 | etf |
| 00878.TW | 國泰永續高股息 | etf |
| 00940.TW | 元大台灣價值高息 | etf |

**代碼格式：** 上市 `代號.TW`、上櫃 `代號.TWO`、美股直接填代號（如 `NVDA`）

### 6-2. 連結到 n8n

開啟「Get row(s) in sheet」節點：

```
Document：選擇「台股 AI 監控清單」試算表
           （Sheet ID：YOUR_GOOGLE_SHEET_ID_HERE）
Sheet Name：工作表1（gid=0）
Credentials：Google Sheets account
```

---

## 7. 流程 A：每日定時分析（逐節點完整說明）

---

### A-1 節點：每日收盤後觸發（Schedule Trigger）

**節點類型：** `n8n-nodes-base.scheduleTrigger`

**Cron 設定：**

```
Cron Expression：0 0 16 * * 1-5
格式說明：秒(0) 分(0) 時(16) 日(*) 月(*) 週(1-5 = 週一至週五)
工作流時區：Asia/Taipei（在 Workflow Settings 中設定）
實際觸發時間：台北時間每週一至週五 下午 16:00:00
```

> 若想改為收盤後立即觸發，可改為 `0 30 14 * * 1-5`（14:30）。

---

### A-2 節點：Get row(s) in sheet（Google Sheets）

**節點類型：** `n8n-nodes-base.googleSheets`

**完整設定：**

```
Operation：Get Row(s)
Document ID：YOUR_GOOGLE_SHEET_ID_HERE
Sheet Name：工作表1（gid=0）
Credentials：Google Sheets account（OAuth2）
```

**輸出：** 每一列產生一個 item，包含 `ticker`、`name`、`type` 欄位。

---

### A-3 節點：取得 Yahoo Finance 資料（HTTP Request）

**節點類型：** `n8n-nodes-base.httpRequest`

**完整設定：**

```
Method：GET
URL：https://query2.finance.yahoo.com/v8/finance/chart/{{ $json.ticker }}

Query Parameters：
  interval = 1d
  range    = 3mo
  events   = div

Headers：
  User-Agent = Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0
  Accept     = text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8

Options：
  Timeout：20000 ms
  Retry On Fail：✅ 啟用
  Wait Between Tries：2000 ms（失敗後等2秒重試一次）
```

---

### A-4 節點：計算技術指標（Code）

**節點類型：** `n8n-nodes-base.code`  
**執行模式：** `runOnceForEachItem`（每個標的各執行一次）

**完整程式碼：**

```javascript
// 取得對應的清單資料（n8n 透過 item pairing 自動對應）
const source = $('Get row(s) in sheet').item.json;

// 處理 API 錯誤或空回應
if (!$json.chart?.result?.[0]) {
  const errMsg = $json.chart?.error?.description || '資料取得失敗';
  return { ...source, error: true, errorMsg: errMsg };
}

const chart = $json.chart.result[0];
const meta  = chart.meta;
const q     = chart.indicators.quote[0];

// 過濾 null 值
const closes  = (q.close  || []).filter(v => v != null);
const highs   = (q.high   || []).filter(v => v != null);
const lows    = (q.low    || []).filter(v => v != null);
const volumes = (q.volume || []).filter(v => v != null);

if (closes.length < 20) {
  return { ...source, error: true, errorMsg: `資料筆數不足 (${closes.length} 筆)` };
}

// ── 指標計算函式 ──────────────────────────────────────────
function sma(data, n) {
  if (data.length < n) return null;
  return +(data.slice(-n).reduce((a, b) => a + b, 0) / n).toFixed(2);
}

function ema(data, n) {
  if (data.length < n) return null;
  const k = 2 / (n + 1);
  let val = data.slice(0, n).reduce((a, b) => a + b, 0) / n;
  for (let i = n; i < data.length; i++) val = data[i] * k + val * (1 - k);
  return +val.toFixed(2);
}

function rsi(data, n = 14) {
  if (data.length < n + 1) return null;
  const changes = data.slice(-n - 1);
  let gains = 0, losses = 0;
  for (let i = 1; i < changes.length; i++) {
    const d = changes[i] - changes[i - 1];
    if (d > 0) gains += d; else losses -= d;
  }
  const ag = gains / n, al = losses / n;
  if (al === 0) return 100;
  return +(100 - 100 / (1 + ag / al)).toFixed(2);
}

// ── 計算指標 ─────────────────────────────────────────────
const currentPrice = +(meta.regularMarketPrice || closes.at(-1)).toFixed(2);
const prevClose    = closes.at(-2);
const priceChange  = +((currentPrice - prevClose) / prevClose * 100).toFixed(2);

const sma5  = sma(closes, 5);
const sma20 = sma(closes, 20);
const sma60 = sma(closes, Math.min(60, closes.length));
const ema12 = ema(closes, 12);
const ema26 = ema(closes, 26);
const macd  = (ema12 != null && ema26 != null) ? +(ema12 - ema26).toFixed(2) : null;
const rsi14 = rsi(closes, 14);

const periodHigh = +Math.max(...highs).toFixed(2);
const periodLow  = +Math.min(...lows).toFixed(2);

const avgVol30  = Math.round(volumes.slice(-30).reduce((a, b) => a + b, 0) / Math.min(30, volumes.length));
const latestVol = volumes.at(-1);
const volRatio  = avgVol30 > 0 ? +(latestVol / avgVol30).toFixed(2) : null;

// 判斷均線排列
const maTrend = (sma5 && sma20 && sma60)
  ? (sma5 > sma20 && sma20 > sma60 ? '多頭排列' : sma5 < sma20 && sma20 < sma60 ? '空頭排列' : '交叉整理')
  : '資料不足';

return {
  ticker: source.ticker,
  name:   source.name,
  type:   source.type,
  currentPrice,
  priceChange,
  sma5, sma20, sma60,
  ema12, ema26,
  macd,
  rsi14,
  maTrend,
  periodHigh, periodLow,
  avgVol30, latestVol, volRatio,
  currency: meta.currency || 'TWD',
  error: false
};
```

**指標說明：**

| 指標 | 計算方式 | 說明 |
|------|---------|------|
| SMA5/20/60 | 近N日收盤價算術平均 | 短/中/長期趨勢線 |
| EMA12/26 | 指數加權移動平均 | MACD 的基礎 |
| MACD | EMA12 − EMA26 | 正值偏多，負值偏空 |
| RSI14 | 近14日漲跌幅相對強弱 | >70 超買，<30 超賣 |
| 均線排列 | SMA5 vs SMA20 vs SMA60 | 多頭/空頭/交叉整理 |
| 量比 | 今日量 ÷ 近30日均量 | >1.5 放量，<0.7 縮量 |

---

### A-5 節點：彙整所有標的資料（Aggregate）

**節點類型：** `n8n-nodes-base.aggregate`

**設定：**

```
Aggregate：Aggregate All Item Data
Destination Field Name：allData
```

所有標的的指標物件被收集進 `allData` 陣列，讓下一節點可以統一處理。

---

### A-6 節點：組建 Claude 分析提示詞（Code）

**節點類型：** `n8n-nodes-base.code`  
**執行模式：** `runOnceForAllItems`

**完整程式碼：**

```javascript
const allData = $input.first().json.allData;
const today   = new Date().toLocaleDateString('zh-TW', { timeZone: 'Asia/Taipei' });

const valid  = allData.filter(d => !d.error);
const errors = allData.filter(d =>  d.error);

// 全部失敗：不呼叫 Claude，直接標記 skipClaude
if (valid.length === 0) {
  return [{ json: {
    claudeBody: null,
    errors,
    skipClaude: true
  }}];
}

// ── 格式化資料為可讀文字供 Claude 分析 ──────────────────
const fmt = d => [
  `【${d.name} (${d.ticker})】類型：${d.type === 'stock' ? '個股' : 'ETF'}`,
  `  現價：${d.currentPrice} ${d.currency}  (${d.priceChange > 0 ? '+' : ''}${d.priceChange}%)`,
  `  RSI14：${d.rsi14 ?? 'N/A'}  MACD：${d.macd ?? 'N/A'}  均線排列：${d.maTrend}`,
  `  SMA5/20/60：${d.sma5}/${d.sma20}/${d.sma60}`,
  `  區間高/低：${d.periodHigh}/${d.periodLow}`,
  `  量比（今/30日均）：${d.volRatio ?? 'N/A'}x`,
].join('\n');

const dataText = valid.map(fmt).join('\n\n');

// ── System Prompt ──────────────────────────────────────
const systemPrompt =
  `你是一位專業的台股技術分析師，兼顧個股波段操作與ETF資產配置策略。` +
  `今天日期：${today}。` +
  `請只根據提供的技術指標進行分析。` +
  `絕對只回覆純 JSON 陣列，不含任何 markdown、說明或換行前綴。`;

// ── User Prompt ────────────────────────────────────────
const userPrompt =
  `以下是今日收盤後的市場技術指標，請對每個標的進行分析並給出具體交易建議。\n\n` +
  `${dataText}\n\n` +
  `ETF 分析時請額外考量：大盤趨勢、定期定額合適性，以及當前價位是否適合單筆買進。\n\n` +
  `回覆一個 JSON 陣列，每個物件格式如下（不要遺漏任何欄位）：\n` +
  `[{\n` +
  `  "ticker": "代號含.TW",\n` +
  `  "name": "中文名稱",\n` +
  `  "type": "stock 或 etf",\n` +
  `  "trend": "偏多 或 偏空 或 震盪",\n` +
  `  "action": "買進 或 賣出 或 觀望 或 持續加碼",\n` +
  `  "buy_zone": "建議買進價格區間，如 900-920",\n` +
  `  "stop_loss": "停損價位數字",\n` +
  `  "take_profit": "目標獲利價位數字",\n` +
  `  "reason": "技術面綜合理由，限 80 字"\n` +
  `}]`;

// ── 組裝 Claude API Request Body ───────────────────────
const claudeBody = JSON.stringify({
  model: 'claude-sonnet-4-6',
  max_tokens: 4096,
  system: systemPrompt,
  messages: [{ role: 'user', content: userPrompt }]
});

return [{ json: { claudeBody, errors, skipClaude: false } }];
```

> **批次設計說明**：所有標的一次打包進單一 API 請求，只呼叫 Claude 1 次。相比對每個標的分別呼叫，可節省約 80% 的 Token 費用，並完全避免 Rate Limit 問題。

---

### A-7 節點：是否需要 Claude 分析（IF）

**節點類型：** `n8n-nodes-base.if`

**條件設定：**

```
Left Value：={{ $json.skipClaude }}
Operator：Boolean → equals
Right Value：false

結果：
  True 輸出（skipClaude = false）→ 呼叫 Claude API 分析
  False 輸出（skipClaude = true）→ 格式化全部失敗通知
```

---

### A-8 節點：呼叫 Claude API 分析（HTTP Request）

**節點類型：** `n8n-nodes-base.httpRequest`

**完整設定：**

```
Method：POST
URL：https://api.anthropic.com/v1/messages

Authentication：Generic Credential Type
Generic Auth Type：HTTP Custom Auth
Credential：Custom Auth account
（自動帶入 x-api-key 與 anthropic-version Header）

Body Content Type：Raw
Raw Content Type：application/json
Body：={{ $json.claudeBody }}

Options：
  Timeout：90000 ms（90秒，Claude 分析多個標的需要較長時間）
```

---

### A-9 節點：格式化全部失敗通知（Code）

當所有標的的 Yahoo Finance 資料均取得失敗時執行，不呼叫 Claude API。

**完整程式碼：**

```javascript
const errors = $json.errors || [];
const today  = new Date().toLocaleDateString('zh-TW', { timeZone: 'Asia/Taipei' });
let msg = `⚠️ *台股 AI 分析報告*\n📅 ${today}\n${'─'.repeat(22)}\n\n今日所有標的資料均取得失敗，無法進行分析。`;
if (errors.length > 0) {
  const errList = errors.map(e => `• ${e.name}(${e.ticker})：${e.errorMsg}`).join('\n');
  msg += `\n\n*失敗清單：*\n${errList}`;
}
return [{ json: { message: msg } }];
```

---

### A-10 節點：解析並格式化訊息（Code）

**完整程式碼：**

```javascript
const resp   = $input.first().json;
const prev   = $('組建Claude分析提示詞').first().json;
const errors = prev.errors || [];

// Claude API 錯誤處理
if (resp.error || !resp.content?.[0]?.text) {
  const msg = resp.error?.message || 'API 回應格式異常';
  return [{ json: { message: `⚠️ Claude API 呼叫失敗：${msg}` } }];
}

// ── 三步驟容錯 JSON 解析 ─────────────────────────────────────
// Step 1：直接解析（Claude 遵守指令的最常見情況）
// Step 2：貪婪正則提取（Claude 有前綴說明文字時）
// Step 3：首[到尾]切片（有尾巴文字且含多個]時）
function robustParse(text) {
  const raw = text.trim();
  try { return JSON.parse(raw); } catch(_) {}
  const m = raw.match(/\[[\s\S]*\]/);
  if (m) { try { return JSON.parse(m[0]); } catch(_) {} }
  const li = raw.lastIndexOf(']'), fi = raw.indexOf('[');
  if (fi !== -1 && li > fi) { try { return JSON.parse(raw.slice(fi, li + 1)); } catch(_) {} }
  throw new Error('無法從回應中提取有效 JSON');
}

let analysis = [];
try {
  analysis = robustParse(resp.content[0].text);
  if (!Array.isArray(analysis)) throw new Error('回應不是陣列');
} catch (e) {
  return [{ json: {
    message: `⚠️ Claude 回應解析失敗：${e.message}\n\n原始回應（前600字）：\n${resp.content[0].text.substring(0, 600)}`
  }}];
}

// ── Markdown 特殊字符逸脫（防止 * _ ` 破壞 Telegram 格式） ──
const escMd = s => String(s ?? '').replace(/[*_`]/g, '\\$&');

const trendIcon  = { '偏多': '📈', '偏空': '📉', '震盪': '↔️' };
const actionIcon = { '買進': '🟢 買進', '賣出': '🔴 賣出', '觀望': '🟡 觀望', '持續加碼': '💚 持續加碼' };
const typeLabel  = { stock: '🏢 個股', etf: '📊 ETF' };

const today = new Date().toLocaleDateString('zh-TW', {
  timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit'
});

const header = `🤖 *台股 AI 分析報告*\n📅 ${today}\n${'─'.repeat(22)}`;

const items = analysis.map(d => {
  const label  = typeLabel[d.type] || '📌';
  const trend  = trendIcon[d.trend] || '❓';
  const action = actionIcon[d.action] || escMd(d.action);
  return [
    `${label} *${escMd(d.name)}* \`${d.ticker}\``,
    `趨勢：${trend} ${escMd(d.trend)}　建議：${action}`,
    `買進區間：${escMd(d.buy_zone)}`,
    `目標價：${escMd(d.take_profit)}　停損：${escMd(d.stop_loss)}`,
    `📝 ${escMd(d.reason)}`
  ].join('\n');
});

const messages = [header, ...items];

// 附加取得失敗的標的清單
if (errors.length > 0) {
  const errList = errors.map(e => `• ${escMd(e.name)}(${e.ticker})：${escMd(e.errorMsg)}`).join('\n');
  messages.push(`⚠️ *以下標的資料取得失敗，未納入分析：*\n${errList}`);
}

// 所有段落用空行拼接為單一字串 → Telegram 只發一則完整報告
const finalMessage = messages.join('\n\n');

return [{ json: { message: finalMessage } }];
```

---

### A-11 節點：Telegram 發送通知

**節點類型：** `n8n-nodes-base.telegram`

**完整設定：**

```
Operation：Send Message（預設）
Chat ID：YOUR_CHAT_ID_HERE（你的 Telegram Chat ID，傳訊給 @userinfobot 取得）
Text：={{ $json.message }}

Additional Fields：
  Parse Mode：Markdown
  Disable Web Page Preview：✅ 啟用

Credentials：我的專屬台股小幫手Telegram
```

---

## 8. 流程 B：Telegram 即時指令查詢（逐節點完整說明）

---

### B-1 節點：每30秒輪詢（Schedule Trigger）

**節點類型：** `n8n-nodes-base.scheduleTrigger`

**Cron 設定：**

```
Cron Expression：*/30 * * * * *
說明：每30秒執行一次（全天 24 小時）
```

> **為何用輪詢而非 Webhook**：本機部署通常沒有對外 IP，無法讓 Telegram 推送 Webhook。輪詢方式只需本機有網路即可，無需開放任何 Port。

---

### B-2 節點：處理 Telegram 指令（Code）

**節點類型：** `n8n-nodes-base.code`

這是整個流程 B 最核心的節點，自帶完整的 Telegram 長輪詢邏輯。

**完整程式碼：**

```javascript
const fs = require('fs');
const https = require('https');

// ── 設定區（需修改） ──────────────────────────────────
const BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'; // 換成你的 Bot Token（從 @BotFather 取得）
const DATA_DIR = 'C:\\ClaudeBot';
const WATCHLIST_FILE = DATA_DIR + '\\stock_watchlist.json';
const OFFSET_FILE    = DATA_DIR + '\\telegram_offset.json';

// ── 工具函式 ─────────────────────────────────────────
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

function makeRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(body)); } 
        catch(e) { resolve({ ok: false, error: "JSON Parse Error", body: body }); }
      });
    });
    req.on('error', e => resolve({ ok: false, error: e.message }));
    if (options.body) req.write(options.body);
    req.end();
  });
}

async function tgGet(method, params = {}) {
  const url = `https://api.telegram.org/bot${BOT_TOKEN}/${method}`;
  return await makeRequest(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  });
}

async function sendMsg(chatId, text) {
  return await tgGet('sendMessage', { chat_id: chatId, text: text, parse_mode: 'HTML' });
}

// ── 本機檔案讀寫 ──────────────────────────────────────
function loadOffset() {
  try { return parseInt(fs.readFileSync(OFFSET_FILE, 'utf8'), 10) || 0; } catch (e) { return 0; }
}
function saveOffset(offset) {
  try { fs.writeFileSync(OFFSET_FILE, offset.toString(), 'utf8'); } catch (e) {}
}
function loadWatchlist() {
  try {
    const data = JSON.parse(fs.readFileSync(WATCHLIST_FILE, 'utf8'));
    return Array.isArray(data) ? data : [data];
  } catch (e) { return []; }
}
function saveWatchlist(list) {
  try { fs.writeFileSync(WATCHLIST_FILE, JSON.stringify(list, null, 2), 'utf8'); return "OK"; }
  catch (e) { return e.message; }
}

// ── 查詢股票中文名稱（TWSE API） ──────────────────────
async function getStockName(market, code) {
  try {
    const url = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=' + market + '_' + code + '.tw&json=1&delay=0';
    const d = await makeRequest(url, { method: 'GET' });
    return (d && d.msgArray && d.msgArray[0] && d.msgArray[0].n) ? d.msgArray[0].n : code;
  } catch { return code; }
}

// ── 主邏輯 ────────────────────────────────────────────
return (async () => {
  const offset  = loadOffset();
  const updData = await tgGet('getUpdates', { offset: offset, limit: 20, timeout: 5 });

  if (!updData.ok || !updData.result || updData.result.length === 0) {
    return [{ json: { status: "no_new_messages", current_offset: offset } }];
  }

  let lastOffset  = offset;
  let sendLogs    = [];
  let aiRequests  = [];

  for (const upd of updData.result) {
    lastOffset = upd.update_id + 1;
    const msg = upd.message;
    if (!msg || !msg.text) continue;

    const chatId = msg.chat.id;
    const text   = msg.text.trim();
    const parts  = text.split(/\s+/);
    const cmd    = parts[0].toLowerCase();
    const list   = loadWatchlist();

    if (cmd === '/list') {
      // ── /list：顯示監控清單 ──────────────────────────
      if (list.length === 0) {
        sendLogs.push(await sendMsg(chatId, '📋 監控清單是空的\n\n新增範例：/add 2356 49 55'));
      } else {
        let out = '📋 <b>股票監控清單</b>\n\n';
        for (const s of list) {
          const icon = s.enabled ? '✅' : '⏸';
          out += icon + ' <b>' + s.name + '</b> (' + s.code + ')\n';
          out += '  買入: ' + s.buy_price + ' | 賣出: ' + s.sell_price + '\n\n';
        }
        out += '共 ' + list.length + ' 支';
        sendLogs.push(await sendMsg(chatId, out));
      }

    } else if (cmd === '/add') {
      // ── /add 代碼 買入價 賣出價 [名稱]：新增標的 ─────
      if (parts.length < 4) {
        sendLogs.push(await sendMsg(chatId, '❌ 格式：/add 股票代碼 買入價 賣出價'));
        continue;
      }
      const rawCode = parts[1].trim();
      let market = 'tse', code = rawCode;
      if (rawCode.startsWith('otc_')) { market = 'otc'; code = rawCode.slice(4); }
      else if (rawCode.startsWith('tse_')) { market = 'tse'; code = rawCode.slice(4); }

      const buyPrice  = parseFloat(parts[2]);
      const sellPrice = parseFloat(parts[3]);
      if (isNaN(buyPrice) || isNaN(sellPrice)) {
        sendLogs.push(await sendMsg(chatId, '❌ 價格必須是數字'));
        continue;
      }

      let name = parts[4];
      if (!name) {
        // 未提供名稱，自動查詢 TWSE
        name = await getStockName(market, code);
        if (name === code && market === 'tse' && !rawCode.startsWith('tse_')) {
          const otcName = await getStockName('otc', code);
          if (otcName !== code) { market = 'otc'; name = otcName; }
        }
      }

      const exists = list.find(s => s.code === code);
      if (exists) {
        exists.buy_price = buyPrice; exists.sell_price = sellPrice;
        exists.market = market; exists.enabled = true;
        const status = saveWatchlist(list);
        sendLogs.push(await sendMsg(chatId, status === "OK"
          ? '✅ 已更新 <b>' + exists.name + '</b> (' + code + ')'
          : '❌ 存檔失敗: ' + status));
      } else {
        list.push({ code, name, market, buy_price: buyPrice, sell_price: sellPrice, enabled: true });
        const status = saveWatchlist(list);
        sendLogs.push(await sendMsg(chatId, status === "OK"
          ? '✅ 已新增 <b>' + name + '</b> (' + code + ')'
          : '❌ 存檔失敗: ' + status));
      }

    } else if (cmd === '/remove' || cmd === '/del') {
      // ── /remove 代碼：刪除標的 ─────────────────────────
      if (parts.length < 2) { sendLogs.push(await sendMsg(chatId, '❌ 格式：/remove 股票代碼')); continue; }
      const code = parts[1].trim().replace(/^(tse_|otc_)/, '');
      const idx  = list.findIndex(s => s.code === code);
      if (idx === -1) { sendLogs.push(await sendMsg(chatId, '❌ 找不到 ' + code)); continue; }
      const removed = list.splice(idx, 1)[0];
      saveWatchlist(list);
      sendLogs.push(await sendMsg(chatId, '🗑 已移除 <b>' + removed.name + '</b> (' + code + ')'));

    } else if (cmd === '/pause') {
      // ── /pause 代碼：暫停監控 ──────────────────────────
      if (parts.length < 2) { sendLogs.push(await sendMsg(chatId, '❌ 格式：/pause 股票代碼')); continue; }
      const code = parts[1].trim().replace(/^(tse_|otc_)/, '');
      const s    = list.find(s => s.code === code);
      if (!s) { sendLogs.push(await sendMsg(chatId, '❌ 找不到 ' + code)); continue; }
      s.enabled = false;
      saveWatchlist(list);
      sendLogs.push(await sendMsg(chatId, '⏸ 已暫停監控 <b>' + s.name + '</b> (' + code + ')'));

    } else if (cmd === '/resume') {
      // ── /resume 代碼：恢復監控 ─────────────────────────
      if (parts.length < 2) { sendLogs.push(await sendMsg(chatId, '❌ 格式：/resume 股票代碼')); continue; }
      const code = parts[1].trim().replace(/^(tse_|otc_)/, '');
      const s    = list.find(s => s.code === code);
      if (!s) { sendLogs.push(await sendMsg(chatId, '❌ 找不到 ' + code)); continue; }
      s.enabled = true;
      saveWatchlist(list);
      sendLogs.push(await sendMsg(chatId, '▶️ 已恢復監控 <b>' + s.name + '</b> (' + code + ')'));

    } else if (cmd === '/help') {
      // ── /help：指令說明 ────────────────────────────────
      sendLogs.push(await sendMsg(chatId,
        '🤖 <b>股票監控指令</b>\n\n' +
        '/list — 查看清單\n' +
        '/add 代碼 買入價 賣出價 — 新增\n' +
        '/remove 代碼 — 刪除\n' +
        '/pause 代碼 — 暫停\n' +
        '/resume 代碼 — 恢復\n' +
        '輸入「股票代碼」 — 進行 AI 即時分析'
      ));

    } else if (/^\d{4,6}$/.test(cmd)) {
      // ── 輸入4~6位數字：觸發 AI 即時分析 ──────────────
      sendLogs.push(await sendMsg(chatId, `🔍 收到指令！正在請 AI 分析 <b>${cmd}</b>，請稍候約 10~15 秒...`));
      aiRequests.push({
        json: {
          text: cmd,          // 股票代號（純數字，後續節點自動加 .TW）
          chat_id: chatId,    // 使用者 Chat ID
          trigger_ai: true    // 標記需要觸發 AI 分析
        }
      });
    }
  }

  saveOffset(lastOffset);

  // trigger_ai 有資料 → 繼續後續 AI 分析節點
  // 否則（只執行了管理指令） → 回傳狀態，流程在此停止
  if (aiRequests.length > 0) {
    return aiRequests;
  } else {
    return [{ json: { status: "command_processed" } }];
  }
})();
```

**程式碼重點說明：**

| 功能 | 說明 |
|------|------|
| `getUpdates` 輪詢 | 每次取最多 20 筆未讀訊息，timeout: 5 秒 |
| Offset 機制 | 讀寫 `telegram_offset.json`，確保不重複處理同一則訊息 |
| 本機清單 | 讀寫 `stock_watchlist.json`，管理 /add /remove /pause /resume |
| TWSE 名稱查詢 | `/add` 未提供名稱時，自動呼叫 TWSE API 取得中文名稱 |
| AI 分析觸發 | 收到 4~6 位純數字 → 輸出帶 `trigger_ai: true` 的 item |

> ⚠️ **需修改的地方**：將程式碼第2行的 `BOT_TOKEN` 換成你自己的 Telegram Bot Token。

---

### B-3 節點：If（判斷是否觸發 AI）

**節點類型：** `n8n-nodes-base.if`

**設定：**

```
Left Value：={{ $json.trigger_ai }}
Operator：Boolean → is true

結果：
  True 輸出（trigger_ai = true）→ 取得 Yahoo Finance 資料
  False 輸出（只有管理指令）   → 流程結束（無後續節點）
```

---

### B-4 節點：取得 Yahoo Finance 資料1（HTTP Request）

**設定：**

```
Method：GET
URL：=https://query2.finance.yahoo.com/v8/finance/chart/{{ $json.text }}.TW

說明：$json.text 是使用者輸入的數字代碼（如 2330），自動補 .TW 成 2330.TW

Query Parameters：interval=1d, range=3mo, events=div
Headers：User-Agent、Accept（同 A-3 節點）

Options：
  Timeout：20000 ms
  Retry On Fail：✅（失敗後自動重試一次，間隔 2 秒）
```

---

### B-5 節點：計算技術指標1（Code）

**執行模式：** `runOnceForEachItem`

邏輯與 A-4 節點相同，但資料來源（source）改為讀取 `If` 節點輸出：

**程式碼差異（前段）：**

```javascript
// 從 If 節點取得使用者輸入的股票代號
let source = {};
try {
  const tgData = $('If').item.json;
  source = {
    ticker: tgData.text || tgData.message?.text || '未知代碼',
    name: 'Telegram 查詢',  // 暫用預設值，Claude 會自動填入真實名稱
    type: 'Stock'
  };
} catch (e) {
  source = { ticker: '未知', name: '即時查詢', type: 'Stock' };
}

// 後段指標計算邏輯與 A-4 節點完全相同
// ...（省略，詳見 A-4 節點程式碼）
```

---

### B-6 節點：彙整所有標的資料1（Aggregate）

設定與 A-5 節點完全相同（`allData`）。

---

### B-7 節點：組建 Claude 分析提示詞1（Code）

相較於 A-6 節點，有兩處額外優化：

**優化 1 — System Prompt 加入名稱防呆：**

```javascript
const systemPrompt =
  `你是一位專業的台股技術分析師，兼顧個股波段操作與ETF資產配置策略。` +
  `今天日期：${today}。` +
  `請只根據提供的技術指標進行分析。` +
  // ↓ 新增：讓 Claude 自動判斷真實名稱，不照抄「Telegram查詢」
  `【重要提示】：JSON 中的 name 欄位，請務必根據 ticker (如 3149.TW) 自行判斷並填入「真實的台股中文名稱」，絕對不要直接照抄輸入資料中的名稱。` +
  `絕對只回覆純 JSON 陣列，不含任何 markdown、說明或換行前綴。`;
```

**優化 2 — User Prompt JSON 範本加入防呆提示：**

```javascript
`  "name": "真實中文名稱（例如：正達、台積電），請勿填寫 Telegram查詢",\n` +
```

---

### B-8 節點：是否需要 Claude 分析1（IF）

設定與 A-7 節點完全相同（判斷 `skipClaude`）。

---

### B-9 節點：呼叫 Claude API 分析1（HTTP Request）

設定與 A-8 節點完全相同。

---

### B-10 節點：抓取即時K線圖（HTTP Request）

在 Claude 分析完成後，額外取一次 K 線資料供繪圖使用。

**設定：**

```
Method：GET
URL：=https://query1.finance.yahoo.com/v7/finance/chart/{{ $('If').item.json.text }}.TW?range=3mo&interval=1d

Options：
  Response Format：JSON
```

> 此節點取得的資料在「Telegram發送通知1」中被引用，只取近5日收盤價（`.slice(-5)`）繪製折線圖。

---

### B-11 節點：解析並格式化訊息1（Code）

**與 A-10 節點的差異：**

```javascript
// ✅ 明確指定節點名稱，避免 n8n item pairing 取到錯誤資料
const resp   = $('呼叫Claude API分析1').first().json;
const prev   = $('組建Claude分析提示詞1').first().json;

// 後段邏輯（容錯解析、Markdown 格式化）與 A-10 節點完全相同
```

---

### B-12 節點：Telegram 發送通知1（sendPhoto）

**節點類型：** `n8n-nodes-base.telegram`

**完整設定：**

```
Operation：Send Photo（傳送圖片）
Chat ID：YOUR_CHAT_ID_HERE（你的 Telegram Chat ID）

Photo URL（動態 QuickChart 圖表）：
={{
  'https://quickchart.io/chart?c=' + encodeURIComponent(JSON.stringify({
    type: 'line',
    data: {
      labels: ['5天前', '4天前', '3天前', '2天前', '最新'],
      datasets: [{
        label: $('If').item.json.text + ' 近期收盤價',
        data: $('抓取即時K線圖').item.json.chart.result[0].indicators.quote[0].close
               .filter(v => v != null).slice(-5),
        fill: false,
        borderColor: 'rgb(54, 162, 235)'
      }]
    }
  }))
}}

Caption（圖片說明文字）：
={{ $('解析並格式化訊息1').item.json.message || $('解析並格式化訊息1').item.json.text }}

Additional Fields：
  Parse Mode：HTML

Credentials：我的專屬台股小幫手Telegram
```

**QuickChart 圖表邏輯說明：**

1. 從「抓取即時K線圖」節點取近3個月的收盤價陣列
2. 過濾掉 null 值後取最後5筆（近5個交易日）
3. 組成 Chart.js 設定物件 → 轉為 JSON → encodeURIComponent 編碼
4. 拼接到 `https://quickchart.io/chart?c=` 後得到圖片 URL
5. Telegram 直接從這個 URL 下載圖片並發送給使用者

---

## 9. Telegram Bot 指令手冊

### 管理指令（由「處理 Telegram 指令」節點直接回覆）

| 指令格式 | 功能 | 範例 |
|---------|------|------|
| `/help` | 顯示所有指令說明 | `/help` |
| `/list` | 查看目前監控清單 | `/list` |
| `/add 代碼 買入價 賣出價` | 新增標的（自動查詢名稱） | `/add 2330 900 980` |
| `/add 代碼 買入價 賣出價 名稱` | 新增標的（手動指定名稱） | `/add 2330 900 980 台積電` |
| `/remove 代碼` | 刪除標的 | `/remove 2330` |
| `/del 代碼` | 同 /remove | `/del 2330` |
| `/pause 代碼` | 暫停監控（保留資料不刪除） | `/pause 2330` |
| `/resume 代碼` | 恢復已暫停的標的 | `/resume 2330` |

### AI 即時分析（觸發流程 B 的 AI 分析鏈）

| 輸入方式 | 觸發條件 | 說明 |
|---------|---------|------|
| 輸入 4~6 位純數字 | `/^\d{4,6}$/.test(cmd)` | 系統自動補 `.TW`，呼叫 Claude 分析 + 回傳K線圖 |

**範例：**
- 輸入 `2330` → 分析台積電（2330.TW）
- 輸入 `00878` → 分析國泰永續高股息（00878.TW）
- 輸入 `3711` → 分析日月光投控（3711.TW）

> 傳送代碼後，系統先回覆「🔍 正在分析，請稍候...」確認訊息，約 10~15 秒後發送分析圖文。

---

## 10. Telegram 通知訊息範例

### 流程 A — 定時完整報告（單則訊息，Markdown 格式）

```
🤖 台股 AI 分析報告
📅 2026/05/19
──────────────────────

🏢 個股  台積電  `2330.TW`
趨勢：📈 偏多　建議：🟢 買進
買進區間：920-935
目標價：978　停損：905
📝 RSI14 為 58，SMA5 站上 SMA20，均線多頭排列，量比 1.3x 溫和放量，支撐在 SMA20 約 915。

🏢 個股  聯發科  `2454.TW`
趨勢：↔️ 震盪　建議：🟡 觀望
買進區間：1050-1080
目標價：1150　停損：1020
📝 MACD 在零軸下方翻紅，RSI14 為 45，量能縮小，待突破 SMA20 確認後再進場。

📊 ETF  元大台灣50  `0050.TW`
趨勢：📈 偏多　建議：💚 持續加碼
買進區間：185-188
目標價：198　停損：180
📝 大盤偏多格局，RSI14 為 55 尚未超買，位於 SMA20 之上，適合定期定額持續加碼。
```

### 流程 B — 即時查詢（圖片 + 說明文字）

Telegram 發送一張折線圖（近5日收盤價），圖片說明文字為 AI 分析報告。

### 全部取得失敗通知

```
⚠️ 台股 AI 分析報告
📅 2026/05/19
──────────────────────

今日所有標的資料均取得失敗，無法進行分析。

失敗清單：
• 台積電(2330.TW)：資料取得失敗
• 聯發科(2454.TW)：資料筆數不足 (5 筆)
```

---

## 11. 本機檔案說明

「處理 Telegram 指令」節點在 `C:\ClaudeBot\` 下管理兩個檔案：

| 檔案 | 說明 |
|------|------|
| `stock_watchlist.json` | Telegram 指令管理的監控清單 |
| `telegram_offset.json` | 記錄 Telegram 訊息讀取進度 |

**`stock_watchlist.json` 完整格式：**

```json
[
  {
    "code": "2330",
    "name": "台積電",
    "market": "tse",
    "buy_price": 900,
    "sell_price": 980,
    "enabled": true
  },
  {
    "code": "00878",
    "name": "國泰永續高股息",
    "market": "tse",
    "buy_price": 22,
    "sell_price": 26,
    "enabled": false
  }
]
```

**`telegram_offset.json` 格式：**

```
12345678
```

（純數字，記錄上次已處理的 Telegram update_id + 1）

> ⚠️ **重要**：本機 `stock_watchlist.json` 與流程 A 的 Google Sheets 監控清單是**相互獨立的兩套清單**。流程 A 固定讀取 Google Sheets；流程 B 的即時查詢根據使用者即時輸入的代碼執行，不依賴任何清單檔案。

---

## 12. 常見問題與排除

### Q1：Telegram 完全沒反應

1. 確認已向 Bot 傳過訊息（先搜尋 Bot 帳號，點「開始」）
2. 確認「處理 Telegram 指令」節點中的 `BOT_TOKEN` 已換成你的
3. 確認工作流 Active 開關為綠色
4. 查看 n8n Executions 記錄，確認「每30秒輪詢」有在執行

### Q2：即時查詢後等了30秒以上沒回應

最長需等一個輪詢週期（30秒）。若超過 60 秒仍無回應：
- 查看 n8n Executions 確認有無錯誤
- 確認股票代碼為 4~6 位純數字（例如輸入 `2330` 而非 `2330.TW`）

### Q3：AI 分析報告中股票名稱顯示「Telegram查詢」

此問題已在「組建Claude分析提示詞1」的 System Prompt 中加入防呆指令修正。若仍出現，確認你使用的是最新版本的 JSON 檔。

### Q4：Yahoo Finance 取得失敗（429 Too Many Requests）

標的數量較多時可能觸發限速。解法：
- 在「Get row(s) in sheet」之後加 **Wait** 節點（1~2秒間隔）
- 或縮減 Google Sheets 清單至 10 筆以內

### Q5：K 線圖無法發送

1. 確認「抓取即時K線圖」節點有成功取得資料
2. 確認 `quickchart.io` 網路可連通
3. 若 K 線資料為空，可能是 close 陣列全為 null，加入 `.filter(v => v != null)` 確認已在程式碼中

### Q6：Google Sheets 授權失效

n8n → **Credentials** → 找到 `Google Sheets account` → 重新授權。

### Q7：`C:\ClaudeBot\` 目錄無法建立

程式碼中已有 `fs.mkdirSync(DATA_DIR, { recursive: true })` 自動建立邏輯。若在 Docker 中需確保 Volume 已掛載，並修改程式碼中的路徑為 `/ClaudeBot`。

### Q8：Cron 觸發時間不對

確認工作流 **Settings → Timezone** 已設為 `Asia/Taipei`（JSON 中已設定，匯入後自動套用）。

---

## 13. 進階設定建議

### 修改觸發時間

在「每日收盤後觸發」節點修改 Cron（時區 Asia/Taipei）：

| 目標時間 | Cron 表達式 |
|---------|------------|
| 14:30（收盤後）| `0 30 14 * * 1-5` |
| 16:00（目前預設）| `0 0 16 * * 1-5` |
| 09:00（開盤前）| `0 0 9 * * 1-5` |

### 升級模型

在兩個「組建Claude分析提示詞」節點的程式碼中修改：

```javascript
// 改為更高品質的模型（費用約 5 倍）
model: 'claude-opus-4-6'
```

### 加入歷史記錄

在「Telegram發送通知」之前，新增 **Google Sheets Append** 節點，將每次分析結果（日期、ticker、action、buy_zone、stop_loss、take_profit）寫入另一張試算表，建立歷史記錄供日後回測。

### 連結錯誤通知工作流

本 JSON 的 `settings.errorWorkflow` 已填入 ID `eQrVcN2IusmVPUnX`。確認該 ID 對應的錯誤通知工作流存在於你的 n8n 環境中（即 `股票ETF分析錯誤通知.json` 匯入後的 ID）。若不符，在工作流 **Settings → Error Workflow** 重新選擇。

---

## 14. 重要免責聲明

> **本系統所有分析結果均由 AI 根據技術指標自動生成，僅供參考，不構成任何投資建議。**
>
> - 技術分析無法保證未來走勢，AI 模型存在誤判風險
> - 建議先用模擬帳戶或小額部位測試系統實際參考價值
> - 投資有風險，所有交易決策請自行承擔責任
> - 請勿將此系統作為唯一交易依據

---

*本文件由 Claude（Anthropic）根據 `台股及ETF分析通知系統.json` 完整解析生成*
