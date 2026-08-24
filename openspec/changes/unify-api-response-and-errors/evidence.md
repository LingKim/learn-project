# Evidence：统一 API 响应与异常处理

## 实现证据

- `backend/src/xuemian_ai/core/status_codes.py`：集中维护当前使用的数字状态码枚举。
- `backend/src/xuemian_ai/core/responses.py`：提供 `ApiResponse[T]`、`PageResponse[T]`、`success_response()` 和 `page_response()`。
- `backend/src/xuemian_ai/core/errors.py`：提供项目异常基类与 400、401、403、404、409、422、502/503/504 通用异常。
- `backend/src/xuemian_ai/core/problem_details.py`：统一 RFC 9457 错误模型、字段校验详情、404/405、响应头透传、500 脱敏和 OpenAPI 媒体类型。
- `openapi/openapi.json`：包含 `ApiResponse`、`PageResponse`、`ProblemDetails` 与 `ValidationIssue` schema。
- `frontend/src/lib/api/generated/`：由最新 OpenAPI 重新生成；健康检查适配层能够区分 503 `ReadyResponse` 和 Problem Details。

## 自动化验证

2026-08-24 实际执行：

```text
backend/.venv/bin/ruff format src tests
19 files left unchanged（最终轮有 2 files reformatted）

backend/.venv/bin/ruff check src tests
All checks passed!

backend/.venv/bin/mypy
Success: no issues found in 16 source files

backend/.venv/bin/pytest
15 passed in 0.51s

backend/.venv/bin/python -m xuemian_ai.openapi ../openapi/openapi.json
通过

frontend: pnpm openapi:generate
生成成功

frontend: pnpm openapi:check
通过

frontend: pnpm format:check
All matched files use the correct format.

frontend: pnpm lint
通过

frontend: pnpm typecheck
通过

frontend: pnpm test
2 files passed, 7 tests passed
```

## 覆盖场景

- 200/201 成功响应与分页元数据。
- 非法成功状态码和非法分页参数。
- 项目 404 异常及稳定 `error_key`。
- Starlette 404、405 与 `Allow` 响应头。
- 401 的 `WWW-Authenticate` 响应头。
- 422 字段级安全校验详情。
- 500 对外脱敏及 `request_id`。
- OpenAPI 成功模型、分页模型和 `application/problem+json` schema。
- 健康检查 503 降级响应的前端展示。

## 未执行项

- 当前环境未安装 `openspec` CLI，因此未执行 OpenSpec CLI validate；已人工核对目录结构、Requirement 和 Scenario 格式。
- 按本轮约定未执行 Next.js build、Docker build、服务启动或真实外部依赖端到端测试。
- 未执行 Git commit 或 push。
