def split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(end - overlap, end) if end == len(text) else end - overlap
    return chunks
