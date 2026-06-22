from pathlib import Path

# Keep prompts within a reasonable size for free-tier AI usage and to
# avoid excessive token costs. Gemini 2.5 Flash supports far larger
# contexts, but this MVP caps input deliberately — see README for the
# rationale and how to raise it.
MAX_EXTRACTED_CHARS = 50_000


class TextExtractionError(Exception):
    pass


def extract_text(file_path: Path, file_type: str) -> str:
    file_type = file_type.lower()

    if file_type == "txt":
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    elif file_type == "docx":
        text = _extract_docx(file_path)
    elif file_type == "pdf":
        text = _extract_pdf(file_path)
    else:
        raise TextExtractionError(
            f"AI document intelligence doesn't support '{file_type}' files yet. "
            "Supported types: DOCX, PDF, TXT."
        )

    text = text.strip()
    if not text:
        raise TextExtractionError(
            "No readable text could be extracted from this file. It may be "
            "empty, image-only, or scanned without OCR."
        )

    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[:MAX_EXTRACTED_CHARS]

    return text


def _extract_docx(file_path: Path) -> str:
    from docx import Document

    try:
        doc = Document(str(file_path))
    except Exception as e:
        raise TextExtractionError(f"Could not read DOCX file: {e}")

    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _extract_pdf(file_path: Path) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(file_path))
    except Exception as e:
        raise TextExtractionError(f"Could not read PDF file: {e}")

    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)

    return "\n\n".join(pages)
