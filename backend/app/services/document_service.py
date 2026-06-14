from pathlib import Path

from langchain_community.document_loaders import TextLoader


def clean_text(text: str) -> str:
    """
    清洗文档文本内容。

    :param text: 原始文本。
    :return: 去除多余空行后的文本。
    """
    # 解析后的文本先做基础清洗，减少空行和不同换行符对切片的影响。
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def parse_document(path: str) -> str:
    """
    解析上传的知识库文档。

    :param path: 文档本地路径。
    :return: 解析并清洗后的文本。
    """
    suffix = Path(path).suffix.lower()
    if suffix in {".txt", ".md"}:
        # 目前先支持纯文本类文档，后续 PDF/DOCX 可在这里扩展对应 loader。
        documents = TextLoader(path, encoding="utf-8").load()
        return clean_text("\n\n".join(document.page_content for document in documents))
    if suffix == ".pdf":
        raise NotImplementedError("PDF 解析后续会使用 PyMuPDF 实现。")
    raise ValueError(f"不支持的文件类型：{suffix}")
