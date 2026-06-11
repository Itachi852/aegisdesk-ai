from pathlib import Path


def parse_document(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".txt", ".md"}:
        return Path(path).read_text(encoding="utf-8")
    if suffix == ".pdf":
        raise NotImplementedError("PDF parsing will be implemented with PyMuPDF.")
    raise ValueError(f"Unsupported file type: {suffix}")
