# Backend

FastAPI 后端服务，负责用户、会话、知识库、RAG 问答、流式输出和反馈统计。

## 启动

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

## 环境变量

参考 `.env.example` 配置 MySQL、Redis、Qdrant、LLM API Key 和模型名称。
