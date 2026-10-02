# 学面通AI后端

FastAPI 模块化单体，包含认证、个人资料、知识库、文件管理及文档处理。

## 常用命令

```bash
uv sync
uv run uvicorn xuemian_ai.main:app --reload --no-access-log
uv run ruff check .
uv run mypy
uv run pytest
uv run python -m xuemian_ai.openapi ../openapi/openapi.json
```

## 日志约定

后端统一使用 `core.logging.get_logger(__name__)` 获取 structlog logger。事件名使用固定的
`snake_case`，动态技术信息放在结构化字段中；不得记录请求正文、请求头、query string、
凭据、模型输入输出或用户业务正文。

`LOG_FORMAT` 支持 `console` 和 `json`，`LOG_LEVEL` 支持 `DEBUG`、`INFO`、`WARNING`、
`ERROR`、`CRITICAL`。项目中间件已经记录唯一的 `request_completed`，业务代码不得再写
HTTP access log。

## API 响应约定

业务 JSON 路由必须显式声明统一响应模型，响应体 `code` 与真实 HTTP 状态码保持一致：

```python
from fastapi import APIRouter
from pydantic import BaseModel

from xuemian_ai.core.errors import NotFoundError
from xuemian_ai.core.responses import ApiResponse, success_response
from xuemian_ai.core.status_codes import ApiStatusCode

router = APIRouter()


class UserResponse(BaseModel):
    id: int
    name: str


@router.get("/users/{user_id}", response_model=ApiResponse[UserResponse])
async def get_user(user_id: int) -> ApiResponse[UserResponse]:
    if user_id != 1:
        raise NotFoundError("用户不存在", error_key="USER_NOT_FOUND")
    return success_response(UserResponse(id=1, name="示例用户"))


@router.post(
    "/users",
    response_model=ApiResponse[UserResponse],
    status_code=ApiStatusCode.CREATED.value,
)
async def create_user() -> ApiResponse[UserResponse]:
    return success_response(
        UserResponse(id=1, name="示例用户"),
        message="创建成功",
        code=ApiStatusCode.CREATED,
    )
```

分页路由使用 `PageResponse[T]` 与 `page_response()`。HTTP 204、文件和流式响应不套统一响应体；健康检查保持裸响应。业务代码抛项目异常，不直接抛 FastAPI `HTTPException`。


## 文档解析与检索

PDF 使用 PDFium 提取原生文字，仅扫描页按需发送给千问 `qwen3.5-ocr`。DOCX、TXT、Markdown 解析结构文本；内嵌图片不会被当作已理解内容。用户必须先确认 AI 处理说明，worker 才能发送页面/正文。Embedding 使用 `qwen3.7-text-embedding`（1024 维），重排使用 `qwen3-rerank`。所有模型与 endpoint 从 Settings 注入，密钥仅在本机 `.env` 或秘密管理系统保存。

部署需要在确认目标环境后分别执行数据库迁移和 Qdrant 显式初始化，再运行 worker（这些命令会修改目标环境）：

```bash
uv sync
uv run alembic upgrade head
uv run xuemian-ai-init-vectors
uv run xuemian-ai-document-worker
```

应用启动不自动创建 collection。Qdrant 是 1024 维命名向量 `dense` / Cosine，tenant 与 UUID payload 索引由初始化命令创建。运行时拒绝不兼容 schema；Qdrant point 不保存正文。PostgreSQL 存储文本和权限，两路召回前后均复核授权。关键词基线是 jieba 分词 + PostgreSQL FTS，不能称为 BM25。

默认每 worker 并发 1，144 DPI、100 个 OCR 页、12M 像素页面渲染上限、64 MiB 累计 PNG、单模型请求 60 秒、原生解析与 OCR 各 600 秒、120 秒续租、最多 3 次处理尝试。OCR 不提供数值置信度，来源保留 null，空正文、乱码或输出截断禁止发布。分块默认 1200 字符/120 重叠，最多 10000 块。

向量写入并校验后原子发布 PostgreSQL 活动版；失败或取消保留旧版。最后文件关联删除时立即撤权，异步删除向量。每 worker 每分钟逐个版本对账：多余点删除，缺失点重新解析；退休、失败与取消版本可重复清理。无 PostgreSQL 版本记录的未知孤儿扫描、快照恢复、生产质量评测仍待验收。

隔离验证脚本只使用合成数据，创建唯一临时数据库/bucket/collection 后清理，不启停现有 PostgreSQL、Redis：

```bash
uv run python scripts/run_document_integration.py
uv run python scripts/run_document_smoke.py
# 少量真实模型调用，仅发送合成内容
uv run python scripts/run_document_smoke.py --real-models
uv run python scripts/qwen_document_smoke.py
```

2026-10-02 用户明确授权后，业务库 `xuemian_ai` 已升级到 `20261002_01`，正式 collection `xuemian_qwen_text_1024_v1` 已创建并校验。已启动本机 API、文档 worker、文件 worker 与 scheduler，前端使用 Next dev；运行清单在 `.runtime/processes.json`。部署前业务库备份位于 `.runtime/backups/xuemian_ai-before-document-processing-20261002.dump`（受限权限、Git 忽略）。Next.js build 与 Docker image build 未运行。详见 OpenSpec evidence 中的验证边界。

## 学习快速回答与业务迁移

`LEARNING_ANSWER_MODEL=qwen3.8-flash`，使用既有千问密钥与兼容 API，关闭思考并校验结构化输出和引用。首次生成需独立确认 AI 数据处理说明。模型调用不持有数据库事务，不向外部 LangSmith 自动发送正文追踪。

后端开发可按根 AGENTS.md 直接迁移本项目业务库：`backend/.venv/bin/python backend/scripts/migrate_business_database.py`；脚本先核对目标与版本、备份，再迁移并读回。不要启停外部 PostgreSQL/Redis。隔离验证使用 `backend/.venv/bin/python backend/scripts/run_learning_checks.py --real-models --quality`，只发送合成资料，结束清理本次测试数据库与 collection。
