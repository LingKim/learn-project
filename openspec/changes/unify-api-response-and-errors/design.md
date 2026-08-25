# Design：统一 API 响应与异常处理

## 响应边界

业务路由显式声明 `ApiResponse[T]` 或 `PageResponse[T]`，不使用中间件猜测并包装返回值。

普通成功响应：

```json
{
  "code": 200,
  "message": "请求成功",
  "data": {}
}
```

分页成功响应：

```json
{
  "code": 200,
  "message": "查询成功",
  "data": [],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5
  }
}
```

创建成功使用 HTTP 201 且响应体 `code` 为 201。无响应正文操作使用 HTTP 204，不构造响应体。健康检查属于运维接口，保持既有裸响应。

## 状态码与错误语义

项目维护只包含当前真实使用项的 `IntEnum`。HTTP 状态码与响应体数字 `code` 必须一致，不允许用 HTTP 200 包装失败。

可预期失败按语义映射为 400、401、403、404、405、409、422、502、503 或 504。只有未知服务端异常使用 500。

异常响应继续使用 `application/problem+json` 和 RFC 9457 标准字段，同时提供前端通用扩展字段：

```json
{
  "type": "https://xuemian.ai/problems/resource-not-found",
  "title": "资源不存在",
  "status": 404,
  "detail": "指定的记录不存在。",
  "instance": "/api/v1/interviews/123",
  "code": 404,
  "message": "指定的记录不存在。",
  "data": null,
  "error_key": "INTERVIEW_NOT_FOUND",
  "request_id": "..."
}
```

`error_key` 是可选的稳定业务标识；`message` 不作为程序分支条件。`request_id` 同时保留在响应头和错误体中。

## 异常体系

`AppError` 是项目异常基类，携带状态码、对外安全消息、可选 `error_key`、标题、Problem Type 和响应头。项目提供按 HTTP 语义划分的通用子类；业务模块只在需要稳定业务语义时定义更具体的异常。

业务与应用代码不得直接依赖 FastAPI `HTTPException`。全局处理器负责把项目异常转换为 HTTP；框架或路由层产生的 FastAPI/Starlette HTTP 异常也由同一入口标准化，并保留 `WWW-Authenticate`、`Allow` 等必要响应头。

## 参数校验

422 响应包含字段级 `errors`：

```json
{
  "field": "email",
  "message": "输入应为有效字符串"
}
```

字段路径移除 Pydantic 的 `body`、`query`、`path` 等来源前缀后以点号连接。响应不得包含原始输入、异常对象或 Pydantic 内部上下文。

## OpenAPI

成功响应通过泛型 Pydantic 模型进入 schema。Problem Details、字段校验详情和常见错误响应也必须出现在 OpenAPI 中。后端 schema 更新后重新生成前端 client，禁止手工复制 DTO。

## 失败与日志

未知异常记录异常类型、不含原始异常消息与局部变量的安全堆栈位置和路由模板，并由日志上下文关联 `request_id`；对前端只返回固定脱敏消息。不得记录请求正文、凭据、模型密钥或用户业务内容。具体日志契约由 `standardize-backend-logging` 变更维护。
