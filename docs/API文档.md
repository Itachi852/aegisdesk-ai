# API 文档

## 认证

### POST /api/v1/auth/register

用户注册。

请求示例：

```json
{
  "email": "test@example.com",
  "password": "123456"
}
```

响应示例：

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "test@example.com",
    "phone": null
  }
}
```

### POST /api/v1/auth/login

用户登录，返回 access token。

请求示例：

```json
{
  "account": "test@example.com",
  "password": "123456"
}
```

### GET /api/v1/auth/me

查询当前登录用户。

请求头：

```text
Authorization: Bearer jwt-token
```

## 智能问答

### POST /api/v1/chat/stream

SSE 流式问答接口。

请求示例：

```json
{
  "session_id": 1,
  "question": "退货政策是什么？"
}
```

SSE 数据格式：

```text
event: message
data: {"type":"delta","content":"您好"}

event: source
data: {"items":[{"doc_name":"退换货政策.txt","summary":"7天无理由退货","score":0.82}]}

event: done
data: {"sources_count":1}
```

## 知识库

- `POST /api/v1/knowledge/documents` 上传文档
- `GET /api/v1/knowledge/documents` 查询文档列表
- `DELETE /api/v1/knowledge/documents/{document_id}` 删除文档

## 会话

- `GET /api/v1/sessions` 查询历史会话
- `GET /api/v1/sessions/{session_id}` 查询会话详情

## 反馈

- `POST /api/v1/feedback` 提交点赞、踩和文字反馈
