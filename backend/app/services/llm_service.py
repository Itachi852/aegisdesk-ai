import asyncio


async def stream_llm(prompt: str):
    # TODO: replace with Tongyi/OpenAI-compatible streaming API call.
    demo = "这是一个流式回答示例。实际开发时会基于检索到的知识片段生成答案，并附带引用来源。"
    for char in demo:
        await asyncio.sleep(0.02)
        yield char
