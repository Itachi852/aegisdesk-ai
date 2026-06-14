import re

from langchain_text_splitters import RecursiveCharacterTextSplitter


QA_MIN_PAIR_COUNT = 3
QUESTION_PATTERN = re.compile(r"^\s*(?:\d+[.、)]\s*)?(?:Q|q|问|问题)\s*[:：]\s*(.+?)\s*$")
ANSWER_PATTERN = re.compile(r"^\s*(?:A|a|答|答案)\s*[:：]\s*(.+?)\s*$")


def _normal_split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    使用通用递归策略切分普通文档。

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


def _parse_qa_chunks(text: str) -> list[str]:
    """
    从正文中解析 QA 对，并按“一问一答一个 chunk”返回。

    :param text: 清洗后的文档正文。
    :return: QA chunk 列表，无法稳定识别时返回空列表。
    """
    chunks: list[str] = []
    current_question: str | None = None
    current_answer_lines: list[str] = []
    reading_answer = False

    def flush_current_pair() -> None:
        if current_question and current_answer_lines:
            answer = "\n".join(line.strip() for line in current_answer_lines if line.strip()).strip()
            if answer:
                chunks.append(f"Q：{current_question.strip()}\nA：{answer}")

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            if reading_answer and current_answer_lines:
                current_answer_lines.append("")
            continue

        question_match = QUESTION_PATTERN.match(line)
        if question_match:
            flush_current_pair()
            current_question = question_match.group(1).strip()
            current_answer_lines = []
            reading_answer = False
            continue

        answer_match = ANSWER_PATTERN.match(line)
        if answer_match and current_question:
            current_answer_lines = [answer_match.group(1).strip()]
            reading_answer = True
            continue

        # 答案可能包含多行说明，直到遇到下一条问题为止都归入当前 QA。
        if reading_answer and current_question:
            current_answer_lines.append(line)

    flush_current_pair()
    return chunks


def split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    将文档切分为适合向量化和检索的片段。

    :param text: 待切分文本。
    :param chunk_size: 每个切片的最大长度。
    :param overlap: 相邻切片之间的重叠长度。
    :return: 文本切片列表。
    """
    # QA 文档按“一问一答一个 chunk”切分，可以让 Rerank 直接比较问题与答案对，减少长 QA 串在一起导致的低分。
    qa_chunks = _parse_qa_chunks(text)
    if len(qa_chunks) >= QA_MIN_PAIR_COUNT:
        return qa_chunks

    return _normal_split_text(text, chunk_size=chunk_size, overlap=overlap)
