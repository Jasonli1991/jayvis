import pytest

import doc_tool


def test_soffice_missing_is_named_exception():
    assert issubclass(doc_tool.SofficeMissing, Exception)


def test_convert_raises_when_soffice_absent(monkeypatch):
    monkeypatch.setattr(doc_tool, "soffice_path", lambda: None)
    with pytest.raises(doc_tool.SofficeMissing):
        doc_tool.convert_document(b"x", "docx", "pdf")


def test_docx_to_pdf_when_available():
    if doc_tool.soffice_path() is None:
        pytest.skip("未安裝 LibreOffice，略過真實轉檔")
    # 用 soffice 自己先把一個極簡 txt 轉 docx 當輸入，避免綁二進位 fixture
    docx = doc_tool.convert_document(b"hello jayvis", "txt", "docx")
    pdf = doc_tool.convert_document(docx, "docx", "pdf")
    assert pdf[:5] == b"%PDF-"
