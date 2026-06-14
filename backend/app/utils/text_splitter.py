from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    将长文本切分为适合向量化和检索的片段。

    :param text: 待切分文本。
    :param chunk_size: 每个切片的最大长度。
    :param overlap: 相邻切片之间的重叠长度。
    :return: 文本切片列表。
    """
    # 递归切分会优先按段落/句子边界拆分，overlap 用来保留跨片段上下文。
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]
