# API 文档

基础地址：

```text
http://127.0.0.1:8000/api/v1
```

除注册、登录外，其余接口需要携带 JWT：

```http
Authorization: Bearer <access_token>
```

## 1. 用户认证

### 注册

```http
POST /auth/register
Content-Type: application/json
```

请求示例：

```json
{
  "email": "user@example.com",
  "password": "123456"
}
```

或：

```json
{
  "phone": "13800138000",
  "password": "123456"
}
```

响应示例：

```json
{
  "access_token": "jwt token",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "phone": null
  }
}
```

### 登录

```http
POST /auth/login
Content-Type: application/json
```

请求示例：

```json
{
  "account": "user@example.com",
  "password": "123456"
}
```

### 获取当前用户

```http
GET /auth/me
```

## 2. 会话接口

### 创建会话

```http
POST /sessions
```

请求示例：

```json
{
  "title": "新建对话"
}
```

### 会话列表

```http
GET /sessions
```

响应示例：

```json
{
  "items": [
    {
      "id": 1,
      "title": "我要退款",
      "created_at": "2026-06-14T13:00:00",
      "updated_at": "2026-06-14T13:05:00"
    }
  ]
}
```

### 会话详情

```http
GET /sessions/{session_id}
```

响应中包含完整消息、业务意图、反馈、引用来源：

```json
{
  "id": 1,
  "title": "我要退款",
  "messages": [
    {
      "id": 10,
      "session_id": 1,
      "role": "user",
      "content": "我要退款",
      "intent": "after_sales",
      "feedback": null,
      "sources": [],
      "created_at": "2026-06-14T13:00:00"
    }
  ]
}
```

`intent` 使用后端本地关键词分类生成，优先级为：投诉 > 售后问题 > 产品咨询 > 闲聊 > 其他。

### 删除会话

```http
DELETE /sessions/{session_id}
```

删除会话时会同步删除：

- `chat_messages`
- `message_sources`
- `feedbacks`

不会删除每日提问次数记录。

## 3. 聊天接口

### 查询今日额度

```http
GET /chat/quota
```

响应示例：

```json
{
  "limit": 100,
  "used": 5,
  "remaining": 95,
  "available": true
}
```

### 流式问答

```http
POST /chat/stream
Content-Type: application/json
```

请求示例：

```json
{
  "question": "退货政策是什么？",
  "session_id": 1
}
```

如果 `session_id` 为空，后端会自动创建新会话。

#### SSE 数据格式

响应类型：

```http
Content-Type: text/event-stream
```

事件 1：会话信息

```text
event: session
data: {"session_id":1,"user_message_id":10,"intent":"after_sales"}
```

事件 2：处理进度

```text
event: progress
data: {"stage":"retrieve","message":"正在检索知识库..."}
```

`stage` 可能值包括 `preparing`、`intent`、`rewrite`、`retrieve`、`rerank`、`generate`。该事件只用于前端展示当前处理阶段，不会保存为聊天消息。

事件 3：模型增量输出

```text
event: message
data: {"type":"delta","content":"您好"}
```

事件 4：引用来源

```text
event: source
data: {"items":[{"document_id":1,"chunk_id":2,"doc_name":"退换货政策.txt","summary":"7天无理由退货...","score":0.82}]}
```

该事件用于保存 `message_sources` 和后续审计调试；当前前端聊天页不再单独渲染“引用文件：...”区域，知识来源由 AI 回答正文末尾按文档名称和 chunk 摘要聚合展示。

事件 5：完成

```text
event: done
data: {"sources_count":1}
```

事件 6：消息保存完成

```text
event: saved
data: {"message_id":11}
```

## 4. 知识库接口

知识库是企业共享数据。以下接口仍需要登录鉴权，但不会按用户隔离文档；任意登录用户都能查看、上传、删除同一套企业知识库。

### 上传文档

```http
POST /knowledge/documents
Content-Type: multipart/form-data
```

字段：

```text
file: 文档文件
```

当前实现支持 `.txt`、`.md`。上传时会计算文件内容 `sha256` 并按 `file_hash` 去重：同样内容已存在且状态为“就绪”时返回 `409` 和“已存在相同内容的文档”；同样内容正在处理时返回“相同文档正在处理中”；同名但内容不同允许上传。如果正文中能识别出 3 组及以上 `Q/A`、`问/答`、`问题/答案` 结构，会按“一问一答一个 chunk”切分；否则按普通文本递归切分。项目依赖中包含 PyMuPDF，可扩展支持 `.pdf`。

前端上传交互会先插入一条本地“处理中”记录，接口返回后再用后端返回的文档状态覆盖该记录。

响应示例：

```json
{
  "id": 1,
  "name": "退换货政策.txt",
  "file_type": "txt",
  "file_hash": "8f14e45fceea167a5a36dedd4bea2543a1c49d3d0f8d9a4c2a6f0b7e5c9d1a2b3c",
  "status": "就绪",
  "error_message": null,
  "chunk_count": 6,
  "created_at": "2026-06-14T13:00:00"
}
```

### 文档列表

```http
GET /knowledge/documents
```

### 文档详情

```http
GET /knowledge/documents/{document_id}
```

### 删除文档

```http
DELETE /knowledge/documents/{document_id}
```

删除文档时会同步删除 MySQL chunks 和 Qdrant 向量数据。

## 5. 反馈接口

### 提交反馈

```http
POST /feedback
Content-Type: application/json
```

请求示例：

```json
{
  "message_id": 11,
  "rating": "like",
  "comment": "回答准确"
}
```

`rating` 可选值：

```text
like / dislike
```

## 6. 管理统计接口

```http
GET /admin/stats
```

当前为预留接口，返回问答统计和反馈统计的基础结构。
