"""Pollinations.AI 生圖 + 梗圖字幕疊字（Pillow）+ 把中文需求轉成生圖 prompt。

觸發由 bot 端關鍵字 gate 決定（確定性）；本模組負責：
- craft_prompt：用 LLM 把使用者的中文生圖需求轉成 Pollinations 提示（梗圖含字幕）。
- generate：打 Pollinations 生圖；提示格式 `畫面` 或梗圖 `畫面|字幕`（字幕用 Pillow 疊上、避免亂碼）。
"""
import urllib.parse
import urllib.request

import config
from llm import generate as _llm_generate

# 梗圖字幕字型候選（macOS 內建中文字型）；config.IMAGE_GEN_FONT 可覆蓋
_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]

_CRAFT_SYS = (
    "你是生圖 prompt 產生器。把使用者的中文生圖需求轉成 Pollinations 用的提示，"
    "只輸出『一行』、不要解釋、不要加引號。\n"
    "- 一般圖：輸出英文畫面描述（具體、可加風格詞）。\n"
    "- 梗圖：輸出「英文畫面描述|中文字幕」——用半形 | 分隔，左邊只描述畫面（別把字寫進畫面），"
    "右邊是要疊在圖上的字幕。\n"
    "- 若需求含需靠對話理解的指涉（如『三大天王』『那張』『剛剛說的』），請依提供的『近期對話』"
    "判斷實際所指（例如對話在談被動元件，『三大天王』就是電阻/電容/電感 resistor/capacitor/inductor）。\n"
    "例：『畫一隻在月球的貓』→ a cute cat sitting on the moon, starry sky, digital art\n"
    "例：『做個SpaceX暴跌的梗圖』→ a Falcon 9 rocket crashing into the sea, exhaust as a red falling "
    "stock chart, dramatic|暴跌啦"
)


def craft_prompt(request: str, context: str = "") -> str:
    """把中文生圖需求轉成 Pollinations 提示（`畫面` 或 `畫面|字幕`）。
    context 為近期對話文字，供解析『三大天王』之類的指涉。失敗回空字串。"""
    user_msg = (f"近期對話（供你理解指涉）：\n{context}\n\n生圖需求：{request or ''}"
                if context else (request or ""))
    try:
        raw = _llm_generate(model=config.MODEL_GENERAL, system=_CRAFT_SYS,
                            messages=[{"role": "user", "content": user_msg}],
                            max_output_tokens=200)
    except Exception:
        return ""
    return (raw or "").strip().strip('"').strip()


def _split_caption(prompt: str):
    """把提示拆成 (畫面描述, 字幕 或 None)，以第一個 | 分隔。"""
    p = prompt or ""
    if "|" in p:
        visual, caption = p.split("|", 1)
        return visual.strip(), (caption.strip() or None)
    return p.strip(), None


def generate(prompt: str):
    """打 Pollinations 生圖，回 PNG/JPEG bytes；失敗回 None。
    提示含字幕（| 之後）時，生圖要求無文字，再用 Pillow 疊字幕。"""
    visual, caption = _split_caption(prompt)
    if not visual:
        return None
    q = visual + (", flat illustration, no text, no captions, no letters" if caption else "")
    url = (f"https://image.pollinations.ai/prompt/{urllib.parse.quote(q)}"
           f"?width={config.IMAGE_GEN_SIZE}&height={config.IMAGE_GEN_SIZE}"
           f"&model={config.IMAGE_GEN_MODEL}&nologo=true")
    # 一定要帶 User-Agent：Pollinations 會擋掉 Python urllib 預設 UA 的請求
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JAYVIS)"})
    try:
        with urllib.request.urlopen(req, timeout=config.IMAGE_GEN_TIMEOUT_S) as r:
            data = r.read()
    except Exception:
        return None
    if not (data and len(data) > 100):          # 太小視為非圖
        return None
    if caption:
        data = _overlay_caption(data, caption)   # 失敗會回原圖
    return data


def _load_font(size: int):
    from PIL import ImageFont
    for p in ([config.IMAGE_GEN_FONT] if config.IMAGE_GEN_FONT else []) + _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(text: str, font, draw, max_w: int):
    """逐字斷行（中文無空白）；保留原有換行。"""
    lines = []
    for para in (text or "").splitlines() or [""]:
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_w or not cur:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines or [""]


def _overlay_caption(img_bytes: bytes, caption: str) -> bytes:
    """經典梗圖風：字幕置底、粗體白字+黑邊。失敗回原圖。"""
    try:
        from io import BytesIO
        from PIL import Image, ImageDraw
        im = Image.open(BytesIO(img_bytes)).convert("RGB")
        W, H = im.size
        draw = ImageDraw.Draw(im)
        size = max(20, int(H * 0.072))
        font = _load_font(size)
        lines = _wrap(caption, font, draw, int(W * 0.92))
        line_h = int(size * 1.18)
        y = H - line_h * len(lines) - int(H * 0.04)   # 距底 4%
        stroke = max(2, size // 12)
        for ln in lines:
            w = draw.textlength(ln, font=font)
            draw.text(((W - w) / 2, y), ln, font=font, fill="white",
                      stroke_width=stroke, stroke_fill="black")
            y += line_h
        out = BytesIO()
        im.save(out, "JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return img_bytes
