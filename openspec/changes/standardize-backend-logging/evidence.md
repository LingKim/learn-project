# Evidence：统一后端结构化日志

## 实现证据

- `backend/src/xuemian_ai/core/logging.py`：使用 `structlog.stdlib.LoggerFactory` 与 `ProcessorFormatter` 统一业务和标准库日志；提供级别配置、公共字段、上下文管理、递归脱敏与安全异常堆栈。
- `backend/src/xuemian_ai/core/request_context.py`：校验或生成 `request_id`，记录唯一 `request_completed`，使用路由模板并在请求结束后清理上下文。
- `backend/src/xuemian_ai/core/problem_details.py`：未知异常只记录一次 `unhandled_exception` ERROR，并为错误响应保留最终 `X-Request-ID`。
- `backend/src/xuemian_ai/api/health.py`：依赖探测失败只记录依赖名、耗时和异常类型。
- `backend/src/xuemian_ai/main.py`：记录安全的启动/关闭事件；程序化启动关闭 Uvicorn access log 并保留项目日志配置。
- `backend/Dockerfile`：容器启动参数显式使用 `--no-access-log`。
- `backend/tests/test_logging.py`：覆盖 JSON/console、标准库互操作、级别、脱敏、安全异常、请求上下文、4xx/5xx、健康探测和生命周期。

## 自动化验证

2026-08-25 实际执行：

```text
cd backend
uv run ruff format --check .
23 files already formatted

uv run ruff check .
All checks passed!

uv run mypy
Success: no issues found in 16 source files

uv run pytest
27 tests passed in 0.42s
```

额外执行：

```text
docker compose --env-file .env.example config --quiet
通过

git diff --check
通过
```

人工核对本次增量 Specification，共 7 项 Requirement、15 个 Scenario。

## 已验证行为

- structlog 事件与标准库 `logging` 事件共享 JSON schema 和 renderer。
- console 与 JSON 输出保留相同事件语义和公共字段。
- `LOG_LEVEL` 能过滤低优先级日志。
- 嵌套敏感键、Bearer Token、凭据赋值文本和带密码 URL 会被脱敏。
- structlog 与 foreign exception 都只输出异常类型和安全堆栈位置，不输出异常原文。
- 合法外部 `request_id` 被沿用，过长或含控制字符的值被替换为 UUID。
- 并发请求的 `request_id` 不串线，日志只记录路由模板，不记录路径参数值。
- 未知 500 只产生一条 `unhandled_exception` ERROR 和一条请求完成 INFO。
- 可预期 4xx 不产生额外 warning 或 ERROR。
- 依赖探测失败不输出连接信息或异常原文。
- 应用正常启动和关闭分别产生一条生命周期日志。

## 未执行项

- 当前环境没有 `openspec` CLI，因此未执行 OpenSpec CLI validate；已人工核对目录、Requirement 与 Scenario 结构。
- 按确认范围未执行 Next.js build、Docker image build、前端测试、服务启动或外部依赖端到端验证。
- 未配置真实日志采集平台，因此未验证采集、索引、轮转、保留期或告警行为；这些均不在本次范围。
- 未执行 Git commit 或 push。
