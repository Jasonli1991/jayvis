import io
import os

import pytest
from PIL import Image

import image_tool


def _png(size=(120, 80), mode="RGB", color=(180, 90, 60)):
    b = io.BytesIO()
    Image.new(mode, size, color).save(b, format="PNG")
    return b.getvalue()


def _kind(b: bytes) -> str:
    if b[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:5] == b"%PDF-":
        return "pdf"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "?"


def _img(b: bytes) -> Image.Image:
    return Image.open(io.BytesIO(b))


def test_convert_png_to_jpeg():
    assert _kind(image_tool.convert_image(_png(), "png", "jpeg")) == "jpeg"


def test_convert_png_to_pdf():
    assert _kind(image_tool.convert_image(_png(), "png", "pdf")) == "pdf"


def test_convert_normalizes_jpg_alias():
    assert _kind(image_tool.convert_image(_png(), "png", "jpg")) == "jpeg"


def test_convert_rgba_to_jpeg_flattens():
    # RGBA → JPEG（JPEG 無 alpha）不應報錯
    out = image_tool.convert_image(_png(mode="RGBA", color=(180, 90, 60, 128)), "png", "jpeg")
    assert _kind(out) == "jpeg"


def test_resize_width_keeps_aspect():
    out = image_tool.resize_image(_png((120, 80)), "png", width=60)
    assert _img(out).size == (60, 40)


def test_resize_longest_dimension():
    out = image_tool.resize_image(_png((120, 80)), "png", longest=60)
    assert max(_img(out).size) == 60


def test_resize_percent():
    out = image_tool.resize_image(_png((120, 80)), "png", percent=50)
    assert _img(out).size == (60, 40)


def test_resize_sets_dpi():
    out = image_tool.resize_image(_png(), "png", dpi=300)
    dpi = _img(out).info.get("dpi")
    assert dpi and round(dpi[0]) == 300


def test_resize_requires_a_field():
    with pytest.raises(ValueError):
        image_tool.resize_image(_png(), "png")


def test_heic_input_converts():
    pytest.importorskip("pillow_heif")
    import pillow_heif
    pillow_heif.register_heif_opener()
    b = io.BytesIO()
    Image.new("RGB", (50, 40), (10, 120, 200)).save(b, format="HEIF")
    out = image_tool.convert_image(b.getvalue(), "heic", "png")
    assert _kind(out) == "png" and _img(out).size == (50, 40)


def test_remove_background_outputs_png_with_alpha():
    pytest.importorskip("rembg")
    if not os.path.exists(os.path.expanduser("~/.u2net/u2net.onnx")):
        pytest.skip("rembg 模型未下載，略過（避免 CI 拉 170MB）")
    out = image_tool.remove_background(_png())
    assert _kind(out) == "png"
    assert out[25] == 6        # IHDR color type 6 = truecolor + alpha
