"""Pollinations.AI 生圖 + 回覆中的隱藏配圖標記解析 + 梗圖字幕疊字（Pillow）。

標記格式：`[[圖：<英文畫面描述>]]` 或梗圖 `[[圖：<英文畫面描述>|<字幕(可中文)>]]`。
有字幕時：生圖叫 flux 別放字（避免亂碼），再用 Pillow 把字幕以粗體+黑邊疊上去。
"""
import re
import urllib.parse
import urllib.request

import config

# 全形「：」或半形「:」都吃；非貪婪，可跨行
_MARKER_RE = re.compile(r"\[\[圖[:：]\s*(.+?)\]\]", re.S)

# 梗圖字幕字型候選（macOS 內建中文字型）；config.IMAGE_GEN_FONT 可覆蓋
_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]


def split_marker(text: str):
    """抽出第一個 [[圖：...]] 標記。回 (移除所有標記後的乾淨文字, 標記內容 或 None)。
    標記內容含畫面與可選字幕（以 | 分隔），交給 generate() 解析。"""
    t = text or ""
    m = _MARKER_RE.search(t)
    if not m:
        return t, None
    inner = (m.group(1) or "").strip()
    clean = _MARKER_RE.sub("", t).strip()
    return clean, (inner or None)


def _split_caption(prompt: str):
    """把標記內容拆成 (畫面描述, 字幕 或 None)，以第一個 | 分隔。"""
    p = prompt or ""
    if "|" in p:
        visual, caption = p.split("|", 1)
        return visual.strip(), (caption.strip() or None)
    return p.strip(), None


def generate(prompt: str):
    """打 Pollinations 生圖，回 PNG/JPEG bytes；失敗回 None。
    若標記含字幕（| 之後），生圖時要求無文字，再用 Pillow 疊字幕。"""
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
