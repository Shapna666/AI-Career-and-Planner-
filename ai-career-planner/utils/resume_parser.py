import os
from PyPDF2 import PdfReader


def parse_resume(filepath: str) -> str:
    """Return extracted text from a resume file. Currently supports PDF only."""
    if not os.path.exists(filepath):
        return ""

    text = ""
    if filepath.lower().endswith(".pdf"):
        try:
            reader = PdfReader(filepath)
            for page in reader.pages:
                text += page.extract_text() or ""
        except Exception:
            pass
    else:
        # fallback – read as plain text
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            text = ""
    return text
