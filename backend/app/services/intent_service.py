BUSINESS_INTENT_LABELS = {
    "product_consultation": "产品咨询",
    "after_sales": "售后问题",
    "chat": "闲聊",
    "complaint": "投诉",
    "other": "其他",
}

INTENT_KEYWORDS = (
    # 规则按优先级排列：投诉 > 售后 > 产品咨询 > 闲聊 > 其他。
    (
        "complaint",
        (
            "投诉",
            "不满意",
            "差评",
            "欺骗",
            "态度差",
            "举报",
            "维权",
        ),
    ),
    (
        "after_sales",
        (
            "退款",
            "退货",
            "换货",
            "维修",
            "保修",
            "售后",
            "物流",
            "发票",
            "订单",
        ),
    ),
    (
        "product_consultation",
        (
            "产品",
            "功能",
            "价格",
            "套餐",
            "规格",
            "购买",
            "怎么用",
            "支持什么",
        ),
    ),
    (
        "chat",
        (
            "你好",
            "你是谁",
            "谢谢",
            "再见",
            "你能做什么",
        ),
    ),
)


def classify_business_intent(question: str) -> str:
    """
    根据本地关键词规则识别用户问题的业务意图。

    :param question: 用户问题。
    :return: 业务意图英文编码。
    """
    normalized = question.strip().lower()
    if not normalized:
        return "other"

    # 本地业务分类只做粗粒度标注，不替代 RAG 内部的知识问答/闲聊路由判断。
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return intent
    return "other"


def get_business_intent_keywords(intent: str) -> tuple[str, ...]:
    """
    获取指定业务意图对应的关键词集合。

    :param intent: 业务意图英文编码。
    :return: 关键词元组。
    """
    for item_intent, keywords in INTENT_KEYWORDS:
        if item_intent == intent:
            return keywords
    return ()
