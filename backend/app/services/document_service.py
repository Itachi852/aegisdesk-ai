from pathlib import Path


def clean_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def parse_document(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".txt", ".md"}:
        return clean_text(Path(path).read_text(encoding="utf-8"))
    if suffix == ".pdf":
        raise NotImplementedError("PDF parsing will be implemented with PyMuPDF.")
    raise ValueError(f"Unsupported file type: {suffix}")
