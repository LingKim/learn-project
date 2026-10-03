# 学面通AI后端

FastAPI 模块化单体，包含认证、个人资料、知识库、文件管理、文档处理、快速回答与刷题练习。

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

## 刷题练习与 worker

API 前缀为 `/api/v1/learning/practice`。练习题集、配置方案、题集 revision、attempt、答案、submission、grade、run 与反馈分别持久化；revision/submission/grade 追加版本。来源失效时历史业务结果保留，生成与评分停止，预览不得返回旧原文。客观判分直接执行保存规则；模型只负责配置建议、出题与主观点评。

```bash
uv run xuemian-ai-practice-worker
# 未重新同步命令入口时也可直接执行源码
.venv/bin/python -c 'from xuemian_ai.practice.worker import run; run()'
```

本次迁移 `20261003_03` 仅新增本项目 9 张练习表；正式库执行前须核对目标、current 并完成可恢复备份。本机已完成，详见本期 evidence。Compose 增加 practice-worker 服务；没有构建或启动本期镜像。

隔离验证命令 `.venv/bin/python scripts/run_practice_integration.py` 创建唯一临时数据库，执行 upgrade/downgrade/upgrade 与真实 PostgreSQL/ASGI HTTP + worker 集成；默认结束清理本次库，`--keep` 仅用于合成评测协同，`--cleanup` 受精确名称护栏限制。普通 pytest 中这些集成测试显式 skip，不会清理业务库。

`run_practice_http_smoke.py` 接入已运行的 API/worker，仅创建合成私有练习，通过 `--token-file` 输入临时令牌，禁止将令牌或正文写入共享 evidence。`evaluate_practice_quality.py` 只使用合成四格式材料，检索、出题与拒答的真实分母分别记录。

## 学习资产与精讲 worker

`make knowledge-worker` 运行持久化精讲任务和学习评分 outbox 投影，业务库版本为 `20261003_04`。运行前复用已有 PostgreSQL/Redis 等依赖，不能自行重建外部数据库。配置项为 `.env.example` 中 `KNOWLEDGE_*`；并发默认 2、租约 30 秒、任务上限 180 秒。

新功能迁移通过业务库目标/version 核对、可恢复备份后执行；本轮备份和读回记录见 `openspec/changes/implement-learning-assets/evidence.md`。领域/API/迁移回归可运行 `backend/.venv/bin/python backend/scripts/run_learning_assets_checks.py`，只创建本项目 namespace 的合成测试库，最后自动清理。真实模型测试默认跳过；需显式启用且仅使用合成资料，不得外发用户资料。

## 质量反馈与受管练习提示词（独立分支，未部署）

本批迁移链 `20261003_05 → 06 → 07` 新增 AgentRun、质量工单与提示词领域。只在隔离库验证，本轮未迁移上述业务库。质量正文加密配置为 `.env.example` 的 `DIAGNOSTIC_SNAPSHOT_KEYS` JSON keyring 与 `DIAGNOSTIC_SNAPSHOT_ACTIVE_KEY_ID`；保留旧 key 可读、新 key 写入，未配置有效密钥时拒绝正文保存/读取。密钥仅通过环境/密钥管理注入，不写入源码、日志或交付记录。

在确认目标与备份并获部署授权后，管理员可运行 `.venv/bin/python -m xuemian_ai.prompt_management.cli --admin-user-id <真实管理员UUID>` 初始化实际练习场景草稿。该命令不调用模型、不发布。管理员再在 `/admin/prompts` 校验公共片段及任务模板、显式执行合成评测并发布；评测调用配置中的真实 Qwen provider，需有效密钥。未发布有效活动版本时，新 `practice_generate` 返回 `PROMPT_RUNTIME_UNAVAILABLE`，入队事务不会残留 PracticeRun/AgentRun。旧任务按保存快照执行，停用只影响新任务；其他未纳管场景沿用既有实现。

质量清理由现有文件调度器每日任务接线：撤销/到期/关闭立即拒读，失效正文最长 7 天物理清理。候选回放只比较已记录排序，关键词为 PostgreSQL FTS，不是 BM25，也不证明因果或独立模式延时。完整验证及首期边界见 `../docs/development/quality-prompt-delivery-20261003.md`。
