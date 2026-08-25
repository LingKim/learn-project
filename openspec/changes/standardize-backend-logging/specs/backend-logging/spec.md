# Backend Logging Specification

## Requirement：统一结构化日志处理链

后端业务日志、Uvicorn error 日志、标准库及第三方库日志必须进入同一日志处理链，并根据配置输出 console 或逐行 JSON。

### Scenario：业务结构化日志

- **WHEN** 项目 logger 写入一个业务事件
- **THEN** 输出包含 `timestamp`、`level`、`event`、`logger`、`service` 和 `environment`
- **AND** 存在请求上下文时包含 `request_id`

### Scenario：标准库日志

- **WHEN** Uvicorn error logger 或第三方库通过标准 `logging` 写入事件
- **THEN** 事件使用与业务日志相同的 renderer 和公共字段
- **AND** 不产生第二种独立日志格式

### Scenario：运行日志级别

- **WHEN** 通过 `LOG_LEVEL` 配置有效日志级别
- **THEN** 低于该级别的事件不输出
- **AND** 非法级别使应用配置明确失败

## Requirement：日志公共 API 保持最小边界

公共日志模块必须负责配置、logger 获取和上下文管理，不得复制日志库的级别方法或接收任意业务 payload。

### Scenario：业务模块记录事件

- **WHEN** 业务模块需要写入日志
- **THEN** 它通过模块名取得 bound logger
- **AND** 直接使用 structlog 的级别方法和固定事件名
- **AND** 不通过自制 `log_info`、`log_error` 等转发函数

## Requirement：请求日志唯一且可关联

每个 HTTP 请求必须获得安全的 `request_id`，并由项目请求中间件产生唯一的请求完成日志。

### Scenario：合法上游请求标识

- **WHEN** `X-Request-ID` 长度为 1–128 且只包含允许的 ASCII 字符
- **THEN** 服务端沿用该标识并绑定到日志上下文、响应头和 request state

### Scenario：缺失或非法上游请求标识

- **WHEN** `X-Request-ID` 缺失、过长或含不允许字符
- **THEN** 服务端生成新的 UUID
- **AND** 非法原值不进入响应或日志

### Scenario：请求完成

- **WHEN** 请求以成功、4xx 或 5xx 状态完成
- **THEN** 只产生一条 `request_completed` INFO 事件
- **AND** 事件包含 method、路由模板、status_code、duration_ms 和 request_id
- **AND** Uvicorn access log 不重复记录该请求

### Scenario：并发请求

- **WHEN** 多个请求并发执行或 worker 复用执行上下文
- **THEN** 各请求日志只包含各自的 request_id
- **AND** 请求结束后不残留上一个请求的上下文

## Requirement：未知异常只记录安全信息

未知服务端异常必须只记录一次 ERROR，并保留可定位但不泄露异常原文或局部变量的安全堆栈。

### Scenario：未知异常

- **WHEN** 请求处理发生未分类异常
- **THEN** 全局异常处理器记录一条 `unhandled_exception` ERROR
- **AND** 请求中间件不再记录第二条异常 ERROR
- **AND** 事件包含异常类型、安全堆栈位置、路由模板和 request_id
- **AND** 日志不包含原始异常消息、局部变量、连接信息、凭据或用户业务正文
- **AND** 客户端继续收到固定脱敏 Problem Details

### Scenario：可预期客户端错误

- **WHEN** 请求返回可预期 4xx
- **THEN** 仅由 `request_completed` 表达结果
- **AND** 不额外记录 warning 或异常事件

## Requirement：敏感信息必须在渲染前脱敏

日志处理链必须递归脱敏凭据、请求载荷和用户业务正文字段，并禁止项目代码把动态用户内容用作事件名。

### Scenario：嵌套敏感字段

- **WHEN** 事件字典或嵌套集合包含敏感键
- **THEN** 对应值在 renderer 执行前被固定占位符替换
- **AND** 大小写变化不得绕过脱敏

### Scenario：异常或自由文本含凭据

- **WHEN** 异常消息或 foreign log 文本含常见凭据模式
- **THEN** 原始异常消息不得进入项目异常事件
- **AND** 文本兜底处理不得输出可复原的凭据片段

## Requirement：依赖探测失败只记录安全技术元数据

就绪检查中的外部依赖探测失败必须记录 warning，同时保持既有健康响应与 OpenAPI 契约。

### Scenario：依赖不可用

- **WHEN** PostgreSQL、Redis 或 RustFS 探测失败
- **THEN** 记录一条 `dependency_check_failed` WARNING
- **AND** 事件只包含固定依赖名、耗时、异常类型和 request_id
- **AND** 不包含 URL、DSN、用户名、原始异常消息或响应正文

## Requirement：应用生命周期具有最小运维日志

应用正常启动和关闭必须产生不含运行秘密的生命周期事件。

### Scenario：应用进入运行状态

- **WHEN** FastAPI lifespan 成功启动
- **THEN** 记录 `application_started` INFO
- **AND** 事件只增加应用版本，不序列化 Settings 或外部依赖地址

### Scenario：应用正常退出

- **WHEN** FastAPI lifespan 正常结束
- **THEN** 记录 `application_stopped` INFO
