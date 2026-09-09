#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shorts_novel_maker.py
=====================
每日自動製作 6 支 Shorts（每支 50 秒）
- 程式啟動時，提供互動式選單讓使用者挑選來源播放清單
- 根據使用者指定的影片類型（小說/禪宗/教學/通用），套用對應的 AI 腳本風格
- 自動生成 AI 背景圖/封面：Claude 生成繪圖提示詞，Pollinations.ai 負責作圖
- 上傳後設定為私人（不自動排程公開）
"""

import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os, json, subprocess, random, re
from pathlib import Path
from datetime import datetime, timedelta, timezone

# 建議將機密金鑰透過 .env 檔案管理，若有裝 python-dotenv 可解開下行註解
# from dotenv import load_dotenv; load_dotenv()

# ============================================================
# 設定
# ============================================================
CONFIG = {
    "shorts": {"width": 1080, "height": 1920, "fps": 30},
    "target_duration": 50,
    "num_shorts": 6,
    "tts": {
        "voice": "zh-TW-HsiaoChenNeural",
        "rate": "-10%",
        "volume": "-5%",
    },
    "output_dir": os.environ.get("SHORTS_OUTPUT_DIR", "./shorts_output"),
    "anthropic_api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
    "pollinations_token": os.environ.get("POLLINATIONS_TOKEN", ""),
    "huggingface_token": os.environ.get("HUGGINGFACE_TOKEN", ""),
    "youtube": {
        "credentials_file": "./client_secrets.json",
        "token_file": "./youtube_token.json",
        "channel_id": "UCzamjcXlE8DWcIotrnv804g",
        "playlist_shorts": "STUDIO",
        "category_id": "22",
    },
    "used_topics_file": "./shorts_used_topics.json",
    "log_file": "./shorts_batch_log.json",
    # 字幕已燒錄進畫面；設為 True 才會額外上傳 YouTube 軟字幕軌（可能造成雙重字幕）
    "upload_caption_track": False,
}

TW = timezone(timedelta(hours=8))

# ============================================================
# Shorts 切入角度
# ============================================================
HOOK_STYLES = [
    # --- 小說 / 故事 ---
    {"id": "suspense",      "name": "懸念鉤子", "video_type": "novel",    "prompt_hint": "用極度懸疑、吊胃口的角度，以「你絕對想不到...」開頭，講述最離奇的片段，讓觀眾非看完整版不可。", "title_prefix": "【震驚】", "color": (30, 0, 60),  "accent": (200, 100, 255)},
    {"id": "emotion",       "name": "情感共鳴", "video_type": "novel",    "prompt_hint": "從角色的極大痛苦、遺憾或蛻變切入，語氣要帶有強烈的情感渲染力，讓觀眾秒入戲。",                     "title_prefix": "【感動】", "color": (30, 10, 20), "accent": (255, 160, 200)},
    {"id": "twist",         "name": "劇情爆點", "video_type": "novel",    "prompt_hint": "聚焦本集最大的逆轉或衝突爆發點，講到最高潮處立刻打住，逼觀眾去看完整版。",         "title_prefix": "【反轉】", "color": (20, 5, 0),   "accent": (255, 140, 0)},
    {"id": "cliffhanger",   "name": "懸崖結局", "video_type": "novel",    "prompt_hint": "截取最危險或最緊張的懸崖結局，用「接下來發生的事，超乎所有人想像...」引爆好奇心。",         "title_prefix": "【結局】", "color": (20, 0, 0),   "accent": (255, 50, 50)},
    
    # --- 禪宗 / 心靈 ---
    {"id": "zen_wisdom",    "name": "當頭棒喝", "video_type": "zen",      "prompt_hint": "精選最震撼的一句禪宗智慧，一語道破現代人的迷惘，風格要犀利且直指人心。",                   "title_prefix": "【智慧】", "color": (10, 15, 30), "accent": (180, 140, 60)},
    {"id": "zen_mindset",   "name": "心靈解藥", "video_type": "zen",      "prompt_hint": "聊現代人最常有的焦慮、內耗或壓力，再用禪宗觀點給出一個豁然開朗的轉念方法。",         "title_prefix": "【感悟】", "color": (15, 20, 10), "accent": (120, 200, 100)},
    {"id": "zen_life",      "name": "人生哲學", "video_type": "zen",      "prompt_hint": "用犀利的反問句開頭（例如：你還在為XX煩惱嗎？），帶出一個深刻的人生哲理，讓觀眾對號入座。",               "title_prefix": "【人生】", "color": (20, 10, 5),  "accent": (255, 200, 80)},
    
    # --- 教學 / 知識 ---
    {"id": "teach_painpoint","name": "痛點解方","video_type": "teaching", "prompt_hint": "開頭直接戳中學習者常遇到的一個技術痛點或卡關的地方，然後自信宣告這支影片有完美解法。","title_prefix": "【解密】", "color": (5, 25, 40),  "accent": (50, 200, 255)},
    {"id": "teach_highlight","name": "精華濃縮","video_type": "teaching", "prompt_hint": "提煉教學中最核心的一個觀念或神技巧，用「只要學會這招」的語氣引發觀眾強烈學習動機。",   "title_prefix": "【必學】", "color": (30, 20, 5),  "accent": (255, 180, 50)},
    {"id": "teach_mistake",  "name": "避坑指南","video_type": "teaching", "prompt_hint": "指出一個90%新手都會犯的致命錯誤，並暗示這部影片會教你如何避開，引發危機感。", "title_prefix": "【避坑】", "color": (40, 10, 10), "accent": (255, 100, 100)},
    
    # --- 通用 / 混合 ---
    {"id": "gen_curiosity", "name": "好奇心引發", "video_type": "general", "prompt_hint": "挑選影片中最反常、最特別或最勾起好奇心的概念作為開頭，不暴雷結果。", "title_prefix": "【揭秘】", "color": (20, 20, 40), "accent": (100, 150, 255)},
    {"id": "gen_core",      "name": "核心價值", "video_type": "general", "prompt_hint": "用最精簡有力的語言，告訴觀眾為什麼這部影片值得他們花時間看。", "title_prefix": "【精華】", "color": (20, 40, 20), "accent": (100, 255, 150)},
]

# ============================================================
# 資料存取輔助
# ============================================================
def load_used_topics():
    if os.path.exists(CONFIG["used_topics_file"]):
        with open(CONFIG["used_topics_file"], "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_used_topic(key, title):
    d = load_used_topics()
    d.setdefault(key, [])
    if title not in d[key]:
        d[key].append(title)
    with open(CONFIG["used_topics_file"], "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

# ============================================================
# YouTube 認證與抓取
# ============================================================
_yt_client = None
def get_youtube():
    global _yt_client
    if _yt_client: return _yt_client
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import pickle

    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
    creds = None
    if os.path.exists(CONFIG["youtube"]["token_file"]):
        with open(CONFIG["youtube"]["token_file"], "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CONFIG["youtube"]["credentials_file"], SCOPES)
            creds = flow.run_local_server(port=8080)
        with open(CONFIG["youtube"]["token_file"], "wb") as f:
            pickle.dump(creds, f)
    _yt_client = build("youtube", "v3", credentials=creds)
    return _yt_client

def interactive_select_playlists():
    youtube = get_youtube()
    print("\n" + "="*50)
    print("正在獲取您的頻道播放清單...")
    
    playlists = []
    next_page = None
    while True:
        try:
            resp = youtube.playlists().list(
                part="snippet,contentDetails", mine=True, maxResults=50, pageToken=next_page
            ).execute()
            for item in resp.get("items", []):
                playlists.append({
                    "id": item["id"], 
                    "title": item["snippet"]["title"],
                    "count": item["contentDetails"]["itemCount"]
                })
            next_page = resp.get("nextPageToken")
            if not next_page: break
        except Exception as e:
            print(f"[ERR] 獲取播放清單失敗: {e}")
            sys.exit(1)

    if not playlists:
        print("[ERR] 您的頻道找不到任何播放清單！")
        sys.exit(1)

    print("\n【請選擇要抽選 Shorts 的來源播放清單】")
    for i, pl in enumerate(playlists):
        print(f"[{i+1:>2}] {pl['title']} (共 {pl['count']} 部影片)")
        
    choice = input("\n請輸入清單編號 (多選請用逗號分隔，例如 1,3,5): ").strip()
    selected_ids = []
    for c in choice.split(","):
        if c.strip().isdigit():
            idx = int(c.strip()) - 1
            if 0 <= idx < len(playlists):
                selected_ids.append(playlists[idx]["id"])
                
    if not selected_ids:
        print("[ERR] 未選擇有效清單，程式結束。")
        sys.exit(1)

    print("\n【請問這批影片的主要類型是？(這將決定 AI 腳本的切入角度)】")
    print("[1] 小說/故事類 (懸念、情感、爆點)")
    print("[2] 禪宗/心靈類 (智慧、感悟、解藥)")
    print("[3] 教學/知識類 (痛點、精華、避坑)")
    print("[4] 通用/混合類 (好奇心、核心價值)")
    
    type_choice = input("請選擇類型 (預設 4): ").strip()
    type_map = {"1": "novel", "2": "zen", "3": "teaching", "4": "general"}
    video_type = type_map.get(type_choice, "general")
    
    return selected_ids, video_type

def fetch_videos_from_selected(selected_ids, video_type, required_count=6):
    youtube = get_youtube()
    all_videos = []
    selected_ids = list(set(selected_ids)) 
    
    for pl_id in selected_ids:
        next_page = None
        while True:
            try:
                resp = youtube.playlistItems().list(
                    part="snippet", playlistId=pl_id, maxResults=50, pageToken=next_page
                ).execute()
                for item in resp.get("items", []):
                    vid_id = item["snippet"]["resourceId"]["videoId"]
                    if vid_id:
                        all_videos.append({
                            "title":       item["snippet"].get("title", ""),
                            "video_id":    vid_id,
                            "url":         f"https://www.youtube.com/watch?v={vid_id}",
                            "description": item["snippet"].get("description", "")[:200],
                            "video_type":  video_type,
                        })
                next_page = resp.get("nextPageToken")
                if not next_page: break
            except Exception as e:
                print(f"      [WARN] 抓取播放清單影片時發生錯誤: {e}")
                break

    if not all_videos:
        return []

    # 依 video_id 去除重複（同一支影片可能同時存在於多個被勾選的清單中）
    unique_videos = list({v["video_id"]: v for v in all_videos}.values())
    if len(unique_videos) < len(all_videos):
        print(f"   [Fetch] 已移除 {len(all_videos) - len(unique_videos)} 支重複影片")

    selected = random.sample(unique_videos, min(required_count, len(unique_videos)))
    print(f"\n   [Fetch] 已從指定的清單中，隨機抽選 {len(selected)} 支影片！")
    return selected

def _resolve_playlist_shorts(youtube, name_or_id):
    if not name_or_id: return ""
    if name_or_id.upper().startswith("PL"): return name_or_id
    try:
        resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
        for item in resp.get("items", []):
            if name_or_id.lower() in item["snippet"]["title"].lower():
                return item["id"]
    except Exception: pass
    return ""

# ============================================================
# AI 腳本與圖片生成
# ============================================================
def _build_prompt(style, source_video, used_str):
    scene  = {"novel": "有聲小說", "zen": "禪宗身心靈", "teaching": "教學與知識分享"}.get(style["video_type"], "綜合內容")
    ending = {"novel": "現在就去看！", "zen": "點進去讓心靜下來！", "teaching": "趕快點進去學起來！"}.get(style["video_type"], "趕快點進去！")
    return f"""你是一位 YouTube Shorts 腳本撰寫師，專門為 {scene} 頻道製作 50 秒短片。
【本次任務】
- 影片標題：{source_video['title']}
- 完整版連結：{source_video['url']}

【{style['name']}風格要求】
{style['prompt_hint']}

【絕對禁止重複的標題】{used_str}
【字數規定】narration 必須剛好 160～180 個中文字，節奏要快（影片僅 50 秒，過長會被截斷）。
【格式規定】narration 是純連續文字，結尾必須說：「完整版連結在下方，{ending}」

【結果格式】只回覆以下 JSON，不含任何其他文字（請確保回傳的是合法的 JSON 格式，不要包含任何 Markdown 標記，例如 ```json）：
{{"title":"（15字以內，不含前綴標籤）","narration":"完整旁白文字", "image_prompt": "（一段簡短英文描述，用來生成符合這支短片氛圍的背景圖，例如：Mysterious dark forest, cinematic lighting, highly detailed, 8k）"}}"""

def generate_shorts_scripts(video_list):
    print(f"\n[AI] 開始生成腳本...")
    client = None
    if CONFIG.get("anthropic_api_key", "").startswith("sk-ant"):
        import anthropic
        client = anthropic.Anthropic(api_key=CONFIG["anthropic_api_key"])
    else:
        print("   " + "!" * 50)
        print("   [警告] 未偵測到 ANTHROPIC_API_KEY（或格式不符 sk-ant 開頭）")
        print("   [警告] 本次將使用『備用罐頭腳本』，每支影片旁白內容雷同！")
        print("   [警告] 若要 AI 生成專屬文案，請先設定環境變數再執行：")
        print("           PowerShell:  $env:ANTHROPIC_API_KEY=\"sk-ant-...\"")
        print("   " + "!" * 50)

    used_data = load_used_topics()
    scripts = []

    for i, source in enumerate(video_list):
        valid_styles = [s for s in HOOK_STYLES if s["video_type"] == source["video_type"]]
        if not valid_styles: 
            valid_styles = [s for s in HOOK_STYLES if s["video_type"] == "general"]
            
        style = random.choice(valid_styles)
        
        used_key = f"shorts_{style['id']}"
        used_str = "、".join(used_data.get(used_key, [])[-8:]) or "無"
        t = source['title']
        print(f"   [{i+1}/{len(video_list)}] 套用: {style['name']} ({t[:15] + ('...' if len(t) > 15 else '')})")

        if client:
            try:
                msg = client.messages.create(
                    model="claude-sonnet-5",
                    max_tokens=800,
                    thinking={"type": "disabled"},  # 簡單文案任務不需思考，關閉可省 token 並加速
                    messages=[{"role": "user", "content": _build_prompt(style, source, used_str)}]
                )
                # Sonnet 5 預設開啟思考功能，content[0] 可能是 ThinkingBlock，
                # 需從所有區塊中取出真正的文字區塊，不能寫死 content[0]
                raw = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
                start_idx, end_idx = raw.find("{"), raw.rfind("}")
                if start_idx != -1 and end_idx != -1:
                    raw = raw[start_idx : end_idx+1]
                data = json.loads(raw)
                title = style["title_prefix"] + re.sub(r'^【[^】]*】', '', data["title"])
                scripts.append({
                    "style": style, "source_video": source, "title": title,
                    "narration": data["narration"],
                    "image_prompt": data.get("image_prompt", f"abstract beautiful background, {style['name']} vibe")
                })
                print(f"      OK: {title}")
                import time as _t; _t.sleep(1)
                continue
            except Exception as e:
                print(f"      [WARN] AI 失敗：{e}，使用備用腳本")

        # 備用腳本
        scripts.append({
            "style": style, "source_video": source,
            "title": style["title_prefix"] + source["title"][:12],
            "narration": f"想看關於「{source['title'][:20]}」的完整內容嗎？這支影片濃縮了最精華的重點，讓你快速掌握核心概念。如果你覺得有收穫，記得點讚訂閱支持頻道。完整版連結在下方，趕快點進去！",
            "image_prompt": f"abstract beautiful background, {style['name']} vibe"
        })
    return scripts

def _download_via_pollinations(prompt, output_path):
    """使用 Pollinations.ai 生成直式圖片（免費、不需額度）"""
    import requests, urllib.parse

    print(f"      [Image] 呼叫 Pollinations 生成中: {prompt[:40]}...")
    enc = urllib.parse.quote(prompt, safe="")
    url = f"https://image.pollinations.ai/prompt/{enc}"
    params = {
        "width": 1080,
        "height": 1920,
        "nologo": "true",
        "seed": random.randint(1, 99999),
        "model": "flux",
    }
    token = CONFIG.get("pollinations_token", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    for attempt in range(1, 3):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=120)
            if response.status_code == 200 and response.content[:3] in (b'\xff\xd8\xff', b'\x89PN'):
                with open(output_path, "wb") as f:
                    f.write(response.content)
                print("      [Image] Pollinations 圖片生成並儲存成功！")
                return True
            else:
                print(f"      [Image] Pollinations 回應錯誤代碼: {response.status_code} - {response.text[:100]}")
        except Exception as e:
            print(f"      [Image] Pollinations 生成失敗（第{attempt}次）: {e}")
        if attempt < 2:
            import time; time.sleep(5)
    return False


def _download_via_huggingface(prompt, output_path):
    """使用 HuggingFace Inference API 生成直式圖片（備援，需 Token 且有額度）"""
    import requests, time

    hf_token = CONFIG.get("huggingface_token", "")
    if not hf_token:
        print("      [Image] 未設定 HUGGINGFACE_TOKEN，跳過 HF 備援")
        return False

    print(f"      [Image] 改用 HuggingFace FLUX 備援生成中: {prompt[:40]}...")

    url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": prompt,
        "parameters": {
            "width": 1080,
            "height": 1920,
            "num_inference_steps": 4,
            "seed": random.randint(1, 99999),
        }
    }

    for attempt in range(1, 4):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=90)
            if response.status_code == 200 and response.content[:3] in (b'\xff\xd8\xff', b'\x89PN'):
                with open(output_path, "wb") as f:
                    f.write(response.content)
                print("      [Image] HuggingFace 圖片生成並儲存成功！")
                return True
            elif response.status_code == 503:
                print(f"      [Image] 模型載入中，等待 20 秒後重試...")
                time.sleep(20)
                continue
            elif response.status_code in (401, 403):
                print(f"      [Image] Token 無效（{response.status_code}），請重新至 huggingface.co 取得")
                return False
            elif response.status_code == 402:
                print(f"      [Image] HuggingFace 額度已耗盡（402），不再重試")
                return False
            else:
                print(f"      [Image] 伺服器回應錯誤代碼: {response.status_code} - {response.text[:100]}")
        except Exception as e:
            print(f"      [Image] 生成失敗（第{attempt}次）: {e}")
        if attempt < 3:
            time.sleep(5)

    return False


def download_ai_image(prompt, output_path):
    """生成直式背景圖：主力 Pollinations.ai（免費），失敗才退回 HuggingFace。"""
    if _download_via_pollinations(prompt, output_path):
        return True
    if _download_via_huggingface(prompt, output_path):
        return True
    print("      [Image] 生圖失敗，使用純色背景")
    return False

# ============================================================
# 影片合成與依賴
# ============================================================
def check_dependencies():
    try:
        if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
            print("[ERR] 找不到 ffmpeg，請安裝"); sys.exit(1)
    except FileNotFoundError:
        print("[ERR] 找不到 ffmpeg，請先安裝並將其加入系統 PATH（https://ffmpeg.org/download.html）"); sys.exit(1)
    try:
        if subprocess.run(["ffprobe", "-version"], capture_output=True).returncode != 0:
            print("[ERR] 找不到 ffprobe，請確認 ffmpeg 完整安裝（含 ffprobe）"); sys.exit(1)
    except FileNotFoundError:
        print("[ERR] 找不到 ffprobe，請確認 ffmpeg 完整安裝並加入系統 PATH（含 ffprobe）"); sys.exit(1)
    try:
        import edge_tts, requests
        from PIL import Image
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        print("[Setup] 偵測到缺少套件，正在安裝中...")
        subprocess.run([sys.executable, "-m", "pip", "install",
                        "edge-tts", "Pillow", "google-api-python-client",
                        "google-auth-oauthlib", "requests", "anthropic"], check=True)
        print("[Setup] 套件安裝完成，請重新執行腳本。")
        sys.exit(0)
    print("[Setup] 依賴套件確認完畢。")

def get_audio_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try: return float(r.stdout.strip())
    except Exception: return 50.0

def get_font(size):
    from PIL import ImageFont
    for fp in ["C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/kaiu.ttf", "C:/Windows/Fonts/mingliu.ttc"]:
        if os.path.exists(fp): return ImageFont.truetype(fp, size)
    return ImageFont.load_default()

def create_hook_card(path, title, style_info, source_title, frame_idx=0, total_frames=1, bg_image_path=None):
    from PIL import Image, ImageDraw, ImageOps # 新增 ImageOps
    import textwrap
    w, h = 1080, 1920
    bg, ac = style_info["color"], style_info["accent"]

    if bg_image_path and os.path.exists(bg_image_path):
        img = Image.open(bg_image_path).convert("RGBA")
        img = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS) # 使用裁切縮放，確保原圖比例不變形
        img = Image.alpha_composite(img, Image.new("RGBA", (w, h), (0, 0, 0, 160))).convert("RGB")
        draw = ImageDraw.Draw(img)
    else:
        img = Image.new("RGB", (w, h), bg)
        draw = ImageDraw.Draw(img)
        for y in range(h):
            draw.line([(0, y), (w, y)], fill=(
                min(255, int(bg[0]+50*(y/h))),
                min(255, int(bg[1]+40*(y/h))),
                min(255, int(bg[2]+60*(y/h)))))

    fn_tag, fn_main, fn_sub, fn_hint = get_font(42), get_font(64), get_font(36), get_font(32)

    tag_text = f"★ {style_info['name']}"
    tx = (w - draw.textbbox((0, 0), tag_text, font=fn_tag)[2]) // 2
    draw.text((tx, h//4), tag_text, font=fn_tag, fill=ac)

    y_pos = h // 4 + 90
    for line in textwrap.wrap(title.replace("【", "").replace("】", " "), width=12):
        lx = (w - draw.textbbox((0, 0), line, font=fn_main)[2]) // 2
        draw.text((lx+2, y_pos+2), line, font=fn_main, fill=(0, 0, 0))
        draw.text((lx, y_pos),     line, font=fn_main, fill=(255, 255, 255))
        y_pos += 80

    y_pos += 40
    st = source_title[:20] + ("..." if len(source_title) > 20 else "")
    lx = (w - draw.textbbox((0, 0), st, font=fn_sub)[2]) // 2
    draw.text((lx, y_pos), st, font=fn_sub, fill=ac)

    hint = "▼ 完整版連結在留言區 ▼"
    draw.text(((w - draw.textbbox((0, 0), hint, font=fn_hint)[2]) // 2, h - 160),
              hint, font=fn_hint, fill=(200, 200, 200))

    dot_y = h - 100
    start_x = w // 2 - (total_frames * 20) // 2
    for i in range(total_frames):
        dx = start_x + i * 20
        draw.ellipse([dx-5, dot_y-5, dx+5, dot_y+5], fill=ac if i == frame_idx else (80, 80, 80))
    img.save(path, quality=95)

def _tts_with_subtitle(text, audio_path, subtitle_path):
    import asyncio, edge_tts
    async def _run():
        c = edge_tts.Communicate(text, CONFIG["tts"]["voice"], rate=CONFIG["tts"]["rate"], volume=CONFIG["tts"]["volume"])
        chunks, words = [], []
        async for chunk in c.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"word": chunk["text"],
                               "start": chunk["offset"]/1e7,
                               "end": (chunk["offset"]+chunk["duration"])/1e7})
        with open(audio_path, "wb") as f:
            for ch in chunks: f.write(ch)
        return words

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        words = loop.run_until_complete(_run())
    except Exception as tts_err:
        err_str = str(tts_err)
        if "403" in err_str:
            raise RuntimeError(
                f"edge-tts 被 Microsoft 拒絕（403）\n"
                f"請手動執行：pip install --upgrade edge-tts\n原始錯誤：{err_str}"
            ) from tts_err
        raise
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    def to_srt(s):
        return f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{int(s%60):02d},{min(999, int(round((s%1)*1000))):03d}"

    with open(subtitle_path, "w", encoding="utf-8") as f:
        if words:
            segments, buf_w, buf_t = [], [], ""
            for i, w in enumerate(words):
                buf_w.append(w); buf_t += w["word"]
                if any(p in w["word"] for p in ",.!?，。！？、") or len(buf_t) >= 9 or i == len(words)-1:
                    segments.append({"text": buf_t.strip(), "start": buf_w[0]["start"], "end": buf_w[-1]["end"]})
                    buf_w, buf_t = [], ""
            for i, seg in enumerate(segments):
                f.write(f"{i+1}\n{to_srt(seg['start'])} --> {to_srt(seg['end'])}\n{seg['text']}\n\n")
        else:
            dur, curr_t = get_audio_duration(audio_path), 0.0
            sentences = [s for s in re.split(r'([,.!?，。！？])', text) if s.strip()]
            for i, s in enumerate(sentences[::2]):
                txt = (s + (sentences[i*2+1] if i*2+1 < len(sentences) else "")).strip()
                if not txt: continue
                end_t = curr_t + (dur * (len(txt) / max(1, sum(len(x) for x in sentences[::2]))))
                clean = re.sub(r'[,.!?，。！？]', '', txt).strip()
                if len(clean) > 16:
                    mid = len(clean) // 2
                    split_pos = mid
                    for offset in range(mid):
                        if clean[mid - offset] == " " or (mid - offset > 0 and "一" <= clean[mid - offset] <= "鿿"):
                            split_pos = mid - offset; break
                        if clean[mid + offset] == " " or (mid + offset < len(clean) and "一" <= clean[mid + offset] <= "鿿"):
                            split_pos = mid + offset; break
                    clean = clean[:split_pos].rstrip() + "\n" + clean[split_pos:].lstrip()
                f.write(f"{i+1}\n{to_srt(curr_t)} --> {to_srt(end_t)}\n{clean}\n\n")
                curr_t = end_t

def make_one_short(script, out_dir, ts_suffix):
    import shutil, tempfile
    style, source, title = script["style"], script["source_video"], script["title"]
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    tmp_dir = out / f"tmp_{ts_suffix}"; tmp_dir.mkdir(exist_ok=True)

    audio_p = str(out / f"sh_{ts_suffix}.mp3")
    sub_p   = str(out / f"sh_{ts_suffix}.srt")
    video_p = str(out / f"sh_{ts_suffix}.mp4")

    try:
        _tts_with_subtitle(script["narration"], audio_p, sub_p)
        dur = min(get_audio_duration(audio_p), CONFIG["target_duration"])

        import time as _time
        _time.sleep(2)
        bg_img = str(tmp_dir / "bg.jpg")
        img_prompt = script.get("image_prompt") or f"abstract cinematic background, {style['name']} vibe, dark atmospheric"
        download_ai_image(img_prompt, bg_img)

        frame_paths = []
        for fi in range(3):
            fp = str(tmp_dir / f"f_{fi:02d}.jpg")
            create_hook_card(fp, title, style, source["title"], fi, 3, bg_img)
            frame_paths.append(fp)

        concat_f = str(tmp_dir / "concat.txt")
        with open(concat_f, "w", encoding="utf-8") as cf:
            for fp in frame_paths:
                cf.write(f"file '{Path(fp).resolve().as_posix()}'\n")
                cf.write(f"duration {dur/3:.3f}\n")
            cf.write(f"file '{Path(frame_paths[-1]).resolve().as_posix()}'\n")

        tmp_nosub = str(tmp_dir / "nosub.mp4")
        r1 = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", concat_f, "-i", audio_p,
                        "-c:v", "libx264", "-preset", "fast", "-r", "30",
                        "-c:a", "aac", "-pix_fmt", "yuv420p", "-color_range", "1",
                        "-t", f"{dur:.3f}", tmp_nosub],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r1.returncode != 0:
            print(f"      [WARN] 影片合成失敗:\n{r1.stderr[-500:]}")
            raise RuntimeError("ffmpeg 影片合成失敗，請檢查 ffmpeg 輸出")

        if os.path.exists(sub_p):
            tmp_sub = os.path.join(tempfile.gettempdir(), f"sh_{ts_suffix}.srt")
            shutil.copy(sub_p, tmp_sub)
            sub_rel = Path(tmp_sub).resolve().as_posix().replace(":", "\\:")
            style_str = "FontName=Microsoft JhengHei,FontSize=20,PrimaryColour=&H00FFFFFF,Outline=2,Alignment=2,MarginV=90,Bold=1"
            r2 = subprocess.run(["ffmpeg", "-y", "-i", tmp_nosub,
                                  "-vf", f"subtitles='{sub_rel}':force_style='{style_str}'",
                                  "-c:a", "copy", video_p],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            try:
                os.remove(tmp_sub)
            except Exception:
                pass
            if r2.returncode != 0:
                print(f"      [WARN] 字幕燒錄失敗，使用無字幕版本:\n{r2.stderr[-300:]}")
                shutil.copy(tmp_nosub, video_p)
        else:
            shutil.copy(tmp_nosub, video_p)

        return video_p, sub_p
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# ============================================================
# 執行主流程
# ============================================================
def run_batch():
    check_dependencies()
    print("=" * 60 + "\n[Shorts 自動製作系統（互動選單版）]\n" + "=" * 60)

    selected_ids, video_type = interactive_select_playlists()

    video_list = fetch_videos_from_selected(selected_ids, video_type, CONFIG["num_shorts"])
    if not video_list:
        print("[ERR] 無法取得影片，結束"); return

    scripts = generate_shorts_scripts(video_list)
    random.shuffle(scripts)

    out_dir, ts = CONFIG["output_dir"], datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []
    youtube = get_youtube()

    # 播放清單 ID 在批次開始時解析一次即可，避免每支影片都重新查詢、浪費 API 配額
    target_playlist_id = _resolve_playlist_shorts(youtube, CONFIG["youtube"]["playlist_shorts"])

    for i, script in enumerate(scripts):
        vtype = script["style"]["video_type"]
        print(f"\n[{i+1}/{len(scripts)}] 正在製作: {script['title']}")
        try:
            video_p, sub_p = make_one_short(script, out_dir, f"{ts}_{i}")

            from googleapiclient.http import MediaFileUpload
            import time
            
            max_retries = 3
            resp = None
            
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        print(f"      [Upload] 重新連線中，第 {attempt+1} 次嘗試上傳...")
                        
                    req = youtube.videos().insert(
                        part="snippet,status",
                        body={
                            "snippet": {
                                "title": script["title"] + " #Shorts",
                                "description": f"{script['narration']}\n\n👇完整版👇\n{script['source_video']['url']}",
                                "tags": ["Shorts", "中文"],
                                "categoryId": CONFIG["youtube"]["category_id"],
                                "defaultLanguage": "zh-TW",
                                "defaultAudioLanguage": "zh-TW",
                            },
                            "status": {
                                "privacyStatus": "private",
                                "selfDeclaredMadeForKids": False,
                            },
                        },
                        media_body=MediaFileUpload(video_p, chunksize=1024*1024*2, resumable=True)
                    )
                    
                    resp_data = None
                    while resp_data is None: 
                        _, resp_data = req.next_chunk()
                        
                    resp = resp_data
                    break
                    
                except Exception as e:
                    print(f"      [WARN] 上傳過程發生錯誤: {e}")
                    if attempt < max_retries - 1:
                        wait_t = 15 * (attempt + 1)
                        print(f"      [Upload] 伺服器強制關閉連線，等待 {wait_t} 秒後重試...")
                        time.sleep(wait_t)
                    else:
                        raise Exception(f"上傳失敗，已達重試上限 ({max_retries}次): {e}")

            _pl_id = target_playlist_id
            if _pl_id:
                try:
                    youtube.playlistItems().insert(
                        part="snippet",
                        body={"snippet": {"playlistId": _pl_id,
                                          "resourceId": {"kind": "youtube#video", "videoId": resp["id"]}}}
                    ).execute()
                    print(f"      [Playlist] 已加入播放清單 {_pl_id}")
                except Exception as e:
                    print(f"      [Playlist] 加入失敗：{e}")

            # 字幕已直接燒錄進畫面，預設不再另外上傳軟字幕軌（避免雙重字幕重疊）。
            # 若想改用 YouTube 可開關的軟字幕，將 CONFIG["upload_caption_track"] 設為 True 即可。
            if CONFIG.get("upload_caption_track") and os.path.exists(sub_p):
                try:
                    youtube.captions().insert(
                        part="snippet",
                        body={"snippet": {
                            "videoId": resp["id"],
                            "language": "zh-TW",
                            "name": "繁體中文",
                            "isDraft": False,
                        }},
                        media_body=MediaFileUpload(sub_p, mimetype="application/x-subrip", resumable=False)
                    ).execute()
                    print(f"      [Caption] 已上傳 zh-TW 字幕軌")
                except Exception as e:
                    print(f"      [Caption] 字幕軌上傳失敗（不影響主影片）：{e}")

            save_used_topic(f"shorts_{script['style']['id']}", script["title"])
            results.append({
                "type": vtype, "title": script["title"],
                "url": f"https://www.youtube.com/watch?v={resp['id']}",
                "status": "OK",
            })
            
            print("      [Sleep] 避免觸發 API 流量限制，暫停 20 秒...")
            time.sleep(20)
            
        except Exception as e:
            results.append({"type": vtype, "title": script["title"], "status": str(e)})

    log_entry = {
        "time":    datetime.now().isoformat(),
        "results": results,
    }
    existing_log = []
    if os.path.exists(CONFIG["log_file"]):
        try:
            with open(CONFIG["log_file"], "r", encoding="utf-8") as f:
                existing_log = json.load(f)
        except Exception:
            existing_log = []
    existing_log.append(log_entry)
    with open(CONFIG["log_file"], "w", encoding="utf-8") as f:
        json.dump(existing_log, f, ensure_ascii=False, indent=2)
    print(f"[LOG] 記錄已寫入 {CONFIG['log_file']}")

    print("\n" + "=" * 60)
    for r in results:
        print(f"  [{r['status']}] {r['type']} | {r['title']} -> {r.get('url', '')}")

if __name__ == "__main__":
    try:
        run_batch()
    except Exception:
        import traceback
        print("\n" + "=" * 60)
        print("[FATAL] 程式發生未預期錯誤，詳細資訊如下：")
        traceback.print_exc()
    finally:
        print("\n" + "=" * 60)
        input("按 Enter 鍵關閉視窗...")