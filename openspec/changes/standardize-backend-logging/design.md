# Design：统一后端结构化日志

## 选型结论

保留 `structlog 26.1.0`。项目已经使用其 `contextvars`、事件字典和 JSON/console renderer；本变更通过 `structlog.stdlib` 完成标准库互操作，不引入 Loguru 或另一套日志门面。

统一处理链路采用 `structlog.stdlib.LoggerFactory`、stdlib `BoundLogger` 与 `ProcessorFormatter`。业务日志和 foreign `LogRecord` 共享时间、级别、logger 名、公共上下文、安全处理和最终 renderer。

## 公共 API 边界

`core.logging` 是唯一公共日志基础设施，职责限定为：

- `configure_logging(settings)`：配置标准库、structlog、Uvicorn logger 和 renderer。
- `get_logger(name)`：返回带模块名的 stdlib-compatible bound logger。
- `bind_context(...)` / `clear_context()`：绑定和清理经过约束的公共上下文。
- 必要时提供仅接受安全请求字段的 `bind_request_context(request_id=...)`。

业务代码直接调用 `logger.info("stable_event_name", ...)`。不得创建只转发 `debug()`、`info()`、`warning()`、`error()` 或接收任意 payload 的公共函数。

## 配置

保留：

- `LOG_FORMAT=console|json`
- `ENVIRONMENT=development|test|production`

新增：

- `LOG_LEVEL=DEBUG|INFO|WARNING|ERROR|CRITICAL`，默认 `INFO`

每条项目日志包含从 `app_name` 派生的 `service` 和现有 `environment`。配置错误必须在启动阶段明确失败，不得静默回退到其他值。

## 稳定日志契约

所有项目事件包含以下公共字段：

```text
timestamp
level
event
logger
service
environment
request_id（存在请求上下文时）
```

事件可以增加经过约束的技术元数据，例如：

```text
method
route
status_code
duration_ms
dependency
exception_type
stack
```

事件名使用稳定的 `snake_case` 常量，不把用户输入拼入 `event`。请求使用路由模板字段，例如 `/api/v1/items/{item_id}`，不得记录可能包含用户值的原始 URL、query string 或请求体。

## 请求上下文

每次请求开始前必须清理 contextvars，防止 worker 复用时串线。

客户端 `X-Request-ID` 仅在满足以下约束时接受：

- 长度为 1–128 个字符。
- 只包含 ASCII 字母、数字、点、下划线、冒号或连字符。

缺失或不合法时由服务端生成 UUID。不合法的原值不得写入日志或响应。最终 `request_id` 绑定到 contextvars、`request.state` 和响应头。

并发请求之间不得共享或覆盖上下文；请求结束后必须清理本次上下文。

## HTTP 请求日志

项目请求中间件是 access log 的唯一事实源，Uvicorn 自带 access log 在所有项目启动入口关闭。Uvicorn error logger 及其他标准库 logger 继续进入统一 ProcessorFormatter。

每次完成的请求只产生一条 `request_completed` INFO 事件，包含：

- `method`
- `route`
- `status_code`
- `duration_ms`
- `request_id`

可预期 4xx 只通过 `request_completed` 表达，不再额外写 warning 或异常日志。

## 未知异常

未知异常只由全局异常处理器写入一次 `unhandled_exception` ERROR。请求中间件不得为同一异常再写 `request_failed` ERROR。

异常事件只包含：

- 异常类型。
- 不含局部变量和原始异常消息的安全堆栈位置。
- 路由模板和 `request_id` 等安全请求上下文。

不得调用会渲染原始异常消息的默认 traceback formatter。对前端仍返回固定脱敏 Problem Details。

本规则细化并取代 `unify-api-response-and-errors` 中“记录完整服务端堆栈”的宽泛描述：保留可定位的调用栈帧，但不保留异常原文或局部变量。

## 健康检查日志

存活检查不访问外部依赖，不新增日志。

就绪检查中的 PostgreSQL、Redis 或 RustFS 每次探测失败时产生一条 `dependency_check_failed` WARNING，只允许包含：

- 固定依赖名。
- 探测耗时。
- 异常类型。
- 当前请求的 `request_id`。

不得记录连接 URL、DSN、用户名、原始异常消息或响应正文。健康响应的既有状态和 OpenAPI 契约保持不变。

## 隐私与脱敏

日志处理链在 renderer 之前递归处理字典、序列和嵌套结构。敏感键匹配不区分大小写，并至少覆盖以下类别：

- 凭据：`password`、`token`、`secret`、`authorization`、`cookie`、`api_key`、`access_key`。
- 请求载荷：`body`、`headers`、`query`、`query_string`。
- 用户业务正文：`prompt`、`content`、`answer`、`resume`、`jd`、`transcript`、`audio`、`recording`。

命中的值以固定占位符替换，不输出长度、前后缀或哈希。自由文本再对常见凭据模式做兜底处理，但该处理不能替代“不得主动记录业务正文”的编码规则。

第三方库默认不启用可能输出 SQL 参数、HTTP 正文或局部变量的 DEBUG/诊断模式。项目 logger 的 `event` 必须是开发者定义的固定文本，不允许直接使用异常消息或用户输入。

## 启动与关闭

应用成功进入 lifespan 后记录 `application_started` INFO，正常退出时记录 `application_stopped` INFO。事件只包含公共字段和应用版本，不包含配置对象或外部依赖地址。启动失败由统一标准库日志链路输出安全错误信息，不打印 Settings 或秘密值。

## 测试策略

单元测试覆盖：

- 日志级别解析和过滤。
- 递归敏感字段脱敏。
- 合法与非法 `X-Request-ID`。
- 安全异常堆栈不包含原始消息和局部变量。

集成测试覆盖：

- JSON 每行可反序列化，公共 schema 稳定。
- console 与 JSON renderer 均能处理业务日志。
- 标准库 logger 与 structlog 使用同一输出格式。
- 并发请求的 contextvars 不串线，请求结束后不残留。
- 成功、4xx 和 5xx 都只有一条 `request_completed`。
- 未知异常只有一条 `unhandled_exception` ERROR。
- 就绪探测失败日志不包含 URL、连接串、异常原文或用户数据。

最终执行 Ruff、mypy 和完整后端 pytest。不执行 Next.js build、Docker image build或外部服务端到端测试。
