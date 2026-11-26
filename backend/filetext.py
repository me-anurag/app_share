"""Read uploaded files for the Review agent: plain text out of PDF / DOCX / TXT, plus similarity checks."""
import hashlib
import re
import zipfile
from html import unescape

MAX_CHARS = 8000


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(path, name):
    """Return {"text", "pages", "words", "kind", "note"} for a stored upload. Never raises."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    try:
        if ext == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(path)
            pages = len(reader.pages)
            parts = []
            for p in reader.pages[:30]:
                parts.append(p.extract_text() or "")
                if sum(map(len, parts)) > MAX_CHARS * 2:
                    break
            text = _tidy(" ".join(parts))
            note = "" if text.strip() else "No selectable text: the PDF is empty or a scanned image."
            return _out(text, pages, "pdf", note)
        if ext == "docx":
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "ignore")
            xml = re.sub(r"</w:p>", "\n", xml)
            text = _tidy(unescape(re.sub(r"<[^>]+>", "", xml)))
            pages = max(1, round(len(text.split()) / 450)) if text else 0
            return _out(text, pages, "docx", "" if text.strip() else "The document has no text.")
        if ext in ("txt", "md", "csv"):
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = _tidy(fh.read(MAX_CHARS * 2))
            return _out(text, 1, ext, "")
    except Exception as e:  # a broken file is itself a finding
        return _out("", 0, ext, f"Could not read the file ({type(e).__name__}). It may be damaged.")
    return _out("", 0, ext, f"{ext.upper() or 'This'} files can't be read as text; only size and type were checked.")


def _tidy(text):
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def _out(text, pages, kind, note):
    return {"text": text[:MAX_CHARS], "truncated": len(text) > MAX_CHARS, "pages": pages,
            "words": len(text.split()), "kind": kind, "note": note}


def shingles(text, k=5):
    words = re.findall(r"\w+", text.lower())
    return {" ".join(words[i:i + k]) for i in range(max(0, len(words) - k + 1))}


def similarity(a, b):
    """Jaccard overlap of 5-word shingles (0..1). Ignores very short texts."""
    sa, sb = shingles(a), shingles(b)
    if len(sa) < 20 or len(sb) < 20:
        return 0.0
    return round(len(sa & sb) / len(sa | sb), 3)
