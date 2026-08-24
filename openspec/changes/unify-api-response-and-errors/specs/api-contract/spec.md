# API Contract Specification

## Requirement：统一业务成功响应

业务 JSON API 必须显式返回包含数字 `code`、文本 `message` 和泛型 `data` 的响应模型，响应体 `code` 必须与真实 HTTP 状态码一致。

### Scenario：普通查询成功

- **WHEN** 业务查询成功并返回 HTTP 200
- **THEN** 响应体 `code` 为 200
- **AND** 响应体包含 `message` 和真实业务 `data`

### Scenario：创建成功

- **WHEN** 资源创建成功并返回 HTTP 201
- **THEN** 响应体 `code` 为 201

### Scenario：无响应正文

- **WHEN** 操作返回 HTTP 204
- **THEN** 响应不得携带统一响应体

### Scenario：健康检查

- **WHEN** 调用存活或就绪端点
- **THEN** 继续返回既有裸健康模型和真实 HTTP 状态
- **AND** 不套用业务成功响应模型

## Requirement：统一分页响应

页码分页接口必须在 `data` 中返回当前页项目列表，并在 `meta` 中返回 `page`、`page_size`、`total` 和 `total_pages`。

### Scenario：空分页结果

- **WHEN** 查询成功但当前页没有项目
- **THEN** `data` 为空数组
- **AND** `meta` 仍包含完整分页信息

## Requirement：统一异常响应

API 错误必须使用真实 4xx 或 5xx HTTP 状态，并以 `application/problem+json` 返回 RFC 9457 标准字段及 `code`、`message`、`data`、可选 `error_key` 和 `request_id` 扩展字段。

### Scenario：业务资源不存在

- **WHEN** 项目异常表达资源不存在
- **THEN** HTTP 状态和响应体 `code/status` 均为 404
- **AND** `data` 为 null
- **AND** `error_key` 可供前端执行稳定业务分支

### Scenario：路由或方法不存在

- **WHEN** Starlette 产生 404 或 405
- **THEN** 响应仍使用统一 Problem Details 结构
- **AND** 405 的 `Allow` 等框架响应头不得丢失

### Scenario：未知异常

- **WHEN** 后端发生未分类异常
- **THEN** 返回 HTTP 500 和固定脱敏消息
- **AND** 服务端日志记录异常堆栈并关联 `request_id`
- **AND** 响应不得泄露堆栈、连接信息或凭据

## Requirement：字段级校验错误

请求参数校验失败必须返回 HTTP 422，并提供不包含原始输入和内部上下文的字段级 `errors`。

### Scenario：请求体字段不合法

- **WHEN** Pydantic 报告一个或多个字段错误
- **THEN** 每个公开错误包含前端可定位的 `field` 和安全 `message`
- **AND** 响应不包含请求输入值、异常对象或内部上下文

## Requirement：OpenAPI 是唯一契约源

统一成功模型、分页模型和 Problem Details 模型必须进入 FastAPI OpenAPI schema，并用于重新生成前端 TypeScript client。

### Scenario：统一契约发生变化

- **WHEN** 后端响应 schema 更新
- **THEN** 导出的 OpenAPI 与生成的前端 client 同步更新
- **AND** 契约一致性检查能够发现陈旧生成物
