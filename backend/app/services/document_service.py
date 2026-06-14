from pathlib import Path

from langchain_community.document_loaders import TextLoader


def clean_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def parse_document(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".txt", ".md"}:
        documents = TextLoader(path, encoding="utf-8").load()
        return clean_text("\n\n".join(document.page_content for document in documents))
    if suffix == ".pdf":
        raise NotImplementedError("PDF 解析后续会使用 PyMuPDF 实现。")
    raise ValueError(f"不支持的文件类型：{suffix}")
