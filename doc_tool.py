"""文件轉檔：LibreOffice headless（soffice --convert-to）。純函式、寫暫存、讀回。"""
import os
import shutil
import subprocess
import tempfile

_SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "soffice",
]


class SofficeMissing(Exception):
    """找不到 LibreOffice/soffice。"""


def soffice_path():
    """回傳可用的 soffice 路徑；找不到回 None。"""
    for c in _SOFFICE_CANDIDATES:
        p = shutil.which(c) if os.path.basename(c) == c else (c if os.path.exists(c) else None)
        if p:
            return p
    return None


def convert_document(in_bytes: bytes, src_ext: str, to_fmt: str) -> bytes:
    """文件互轉（docx/xlsx/pptx/odt/txt/html ↔ pdf 等）。需 LibreOffice。"""
    soffice = soffice_path()
    if soffice is None:
        raise SofficeMissing("未安裝 LibreOffice")
    src_ext = (src_ext or "bin").lstrip(".").lower()
    to_fmt = (to_fmt or "pdf").lstrip(".").lower()
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in." + src_ext)
        with open(src, "wb") as f:
            f.write(in_bytes)
        prof = os.path.join(d, "profile")            # 獨立 profile 避免並發鎖
        r = subprocess.run(
            [soffice, "--headless", f"-env:UserInstallation=file://{prof}",
             "--convert-to", to_fmt, "--outdir", d, src],
            capture_output=True, text=True, timeout=120)
        out = os.path.join(d, "in." + to_fmt)
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError(f"soffice 轉檔失敗：{r.stderr.strip() or r.stdout.strip()}")
        with open(out, "rb") as f:
            return f.read()
