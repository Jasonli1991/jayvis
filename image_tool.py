"""圖片工具：Pillow（格式/尺寸/解析度，跨平台）+ rembg（去背）。純函式、in-memory。"""
import io

try:                                    # HEIC（iPhone/Mac 格式）：有裝外掛才註冊
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

from PIL import Image

# 別名正規化（使用者/模型可能給別名）
_FMT_ALIAS = {"jpg": "jpeg", "tif": "tiff"}
# 正規化格式名 → Pillow 的 format 字串
_PIL_FORMAT = {"jpeg": "JPEG", "png": "PNG", "tiff": "TIFF", "gif": "GIF",
               "bmp": "BMP", "webp": "WEBP", "pdf": "PDF"}


def _norm_fmt(fmt: str) -> str:
    f = (fmt or "").strip().lower().lstrip(".")
    return _FMT_ALIAS.get(f, f)


def _open(in_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(in_bytes))


def _flatten_if_needed(img: Image.Image, fmt: str) -> Image.Image:
    """JPEG/PDF 無 alpha → RGBA/P/LA 先轉 RGB，避免 save 報錯。"""
    if fmt in ("jpeg", "pdf") and img.mode in ("RGBA", "LA", "P"):
        return img.convert("RGB")
    return img


def convert_image(in_bytes: bytes, src_ext: str, to_fmt: str) -> bytes:
    """圖片格式互轉（含 image→pdf）。to_fmt 例：png/jpg/jpeg/tiff/gif/webp/bmp/pdf。"""
    fmt = _norm_fmt(to_fmt)
    if fmt not in _PIL_FORMAT:
        raise ValueError(f"不支援輸出格式：{to_fmt}")
    img = _flatten_if_needed(_open(in_bytes), fmt)
    out = io.BytesIO()
    img.save(out, format=_PIL_FORMAT[fmt])
    return out.getvalue()


def resize_image(in_bytes: bytes, src_ext: str, *, width=None, height=None,
                 longest=None, percent=None, dpi=None) -> bytes:
    """調尺寸/解析度。欄位皆可選，至少要一個有效值。
    width/height：指定該邊像素（單給一邊則另一邊等比）。
    longest：最長邊縮到該值（等比）。percent：依原尺寸百分比縮放。dpi：設定解析度。"""
    has_size = any(v is not None for v in (width, height, longest, percent))
    if not has_size and dpi is None:
        raise ValueError("resize 需至少一個欄位（width/height/longest/percent/dpi）")

    img = _open(in_bytes)
    w0, h0 = img.size
    tw, th = w0, h0
    if percent is not None:
        tw = max(1, round(w0 * float(percent) / 100.0))
        th = max(1, round(h0 * float(percent) / 100.0))
    elif longest is not None:
        scale = float(longest) / max(w0, h0)
        tw, th = max(1, round(w0 * scale)), max(1, round(h0 * scale))
    elif width is not None and height is not None:
        tw, th = int(width), int(height)
    elif width is not None:
        tw = int(width)
        th = max(1, round(h0 * (tw / w0)))
    elif height is not None:
        th = int(height)
        tw = max(1, round(w0 * (th / h0)))
    if (tw, th) != (w0, h0):
        img = img.resize((tw, th), Image.LANCZOS)

    fmt = _norm_fmt(src_ext or "png")
    save_fmt = _PIL_FORMAT.get(fmt, "PNG")
    img = _flatten_if_needed(img, fmt if fmt in _PIL_FORMAT else "png")
    save_kw = {}
    if dpi is not None:
        save_kw["dpi"] = (int(dpi), int(dpi))
    out = io.BytesIO()
    img.save(out, format=save_fmt, **save_kw)
    return out.getvalue()


def remove_background(in_bytes: bytes) -> bytes:
    """去背，回傳含透明通道的 PNG。rembg 不限作業系統；首次會下載模型。"""
    from rembg import remove          # 延遲匯入：未啟用時不付 import 成本
    return remove(in_bytes)
