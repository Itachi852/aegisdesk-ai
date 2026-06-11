# AegisDesk AI

AI 智能客服系统，基于 RAG 架构实现企业知识库问答、流式回答、引用溯源、会话管理与用户反馈。

## 项目结构

```text
backend/      后端服务，FastAPI + MySQL + Qdrant + LLM
frontend/     前端应用，React + TypeScript + Vite
docs/         API、数据库、AI 架构和业务流程文档
项目说明.md   项目整体说明
运行指南.md   本地运行说明
```

## 推荐技术栈

- 前端：React + TypeScript + Vite
- 后端：Python + FastAPI
- 数据库：MySQL
- 向量库：Qdrant
- Embedding：bge-m3
- LLM：通义千问 API 或 OpenAI 兼容接口
- 流式输出：SSE
- 缓存与限流：Redis

## 核心能力

- 用户注册、登录
- 独立会话与历史记录
- 文档上传、解析、切分、向量化
- RAG 智能问答
- SSE 流式输出
- 知识来源引用展示
- 点赞、踩与文字反馈
- 意图识别、追问建议、管理后台统计
