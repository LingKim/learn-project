# Evidence：后端文件上传、知识库文件管理与清理闭环

## 当前阶段

- 状态：后端接口、数据库迁移、RustFS 存储闭环、持久化清理任务和生成契约已实现，等待用户人工验收。
- PRD：已更新为 v0.6；OpenSpec Proposal、Design、Tasks 与三份增量 Specification 已同步。
- 范围：仅交付后端接口与生成契约，不开发内容库前端，不实现文档解析、分块、Embedding/RAG 或病毒扫描。
- Git：本变更保持未提交状态；未经用户当轮授权不 commit、不 push。

## 规格与结构验证

- OpenSpec CLI：当前环境未发现可执行文件，未执行 strict validate，也不以文件结构检查代替官方校验。
- 文件结构检查：Proposal、Design、Tasks、Evidence 与三份增量 Specification 均存在且非空。
- Requirement/Scenario 结构检查：三份 Specification 共 22 条 Requirement、50 个 Scenario，每份 Requirement 均有下游 Scenario 覆盖。
- 文档一致性：正式内容身份统一为服务端 SHA-256；客户端 MD5/SHA-256 仅为不可信会话元数据；上传完成状态为“已上传·待解析”；病毒扫描明确不在本期范围。
- 存储域：初始化 `quarantine`、`documents`、`recordings`、`temporary` 四类 bucket；知识库文件当前只使用前两类，不预建录音或导出业务表。

## 实现范围

- 数据链路：`UploadSession → StoredObject → FileAsset → KnowledgeBaseFile`，有效 `FileAsset` 引用是物理删除事实源，`reference_count` 仅作性能字段。
- 上传：PDF、DOCX、TXT、MD 白名单；类型、结构、大小、页数/字符数、压缩比等边界；单次 PUT、multipart、续签、取消、完成轮询和 24 小时幂等键。
- 去重：服务端流式 SHA-256；同知识库重复返回 409；同用户跨知识库支持关联；跨用户只做不可见物理字节去重，不共享逻辑所有权或下载能力。
- 文件管理：知识库与知识库文件 CRUD、分页/筛选、重命名、移动、短期预签名下载、删除影响预览、一次性确认 token、软删除及最后有效知识库保护。
- 清理：PostgreSQL 持久化任务、租约、重试、`FOR UPDATE SKIP LOCKED`、每天 02:30 调度、每周日 03:30 对账、孤儿双次确认与 7 天保护期、用户删除清理入口、墓碑和技术记录保留清理。
- 生命周期：`StoredObject.generation` 进入删除/修复任务幂等键，防止对象删除后同摘要重新上传时复用旧生命周期任务。
- 安全：审计不记录文件名、摘要、正文、预签名 URL、bucket 或对象 key；生产环境校验 HTTPS endpoint 和非占位凭据。

## 自动化验证

### 后端质量门禁

在 `backend/` 执行：

```text
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```

结果：Ruff、mypy 均通过；pytest 为 `63 passed`。

### 数据库迁移

- 在唯一隔离的临时 PostgreSQL 数据库中，从空库执行完整 Alembic upgrade，成功升级至 `ac3e06160525 (head)`。
- 验证后删除该临时数据库；开发数据库也已升级至同一 head。
- 未启动、停止、重建或删除项目外部 PostgreSQL/Redis 服务。

### RustFS 配置

- `make bootstrap-storage` 已真实执行，确认四个 bucket 存在。
- `quarantine` CORS 仅允许 `PUT,HEAD`；`documents` CORS 仅允许 `GET,HEAD`。
- `quarantine` 与 `temporary` 临时对象生命周期均为 2 天。
- 生产配置会拒绝非 HTTPS endpoint 或占位凭据。

### 真实 curl 全链路

使用 `scripts/curl-file-smoke.sh` 对真实 FastAPI、PostgreSQL、Redis 与 RustFS 执行，已覆盖：

- 类型白名单 422、硬大小限制 413，且 HTTP status 与 body `code` 一致；
- 上传 URL 续签与取消；
- TXT、MD、PDF、DOCX 单次上传；21 MB DOCX multipart 上传；
- `Idempotency-Key` 重放返回同一上传会话；
- 同知识库重复 409、同用户跨知识库 LINK、跨用户逻辑所有权隔离；
- 短期下载 URL、文件重命名、陈旧删除 token 409；
- 文件软删除、异步物理清理、知识库删除和最后有效知识库保护 409。

smoke 清理后的开发库只读核对结果：

```text
smoke_users=0
pending_tasks=0
failed_tasks=0
count_drift=0
non_deleted_zero_ref=0
physical_delete_audits=5
```

### Worker 故障恢复与 Scheduler

- 在唯一隔离数据库运行 `backend/scripts/file_worker_fault_probe.py`：无效 RustFS endpoint 后任务为 `pending|1|EndpointConnectionError`；恢复真实 endpoint 后为 `succeeded|2`。
- 在隔离数据库真实执行一次 daily 调度与 reconciliation：`orphan_candidates=0`、`delete_tasks=0`，没有产生物理删除任务。
- 两项验证结束后均删除临时数据库；未在开发库执行无范围清理或故障注入。

### OpenAPI 与生成契约

- 从 FastAPI 导出 `openapi/openapi.json`，并执行 `pnpm openapi:generate` 更新 generated SDK。
- `pnpm openapi:check`、`pnpm boundaries:check`、`pnpm format:check`、`pnpm lint`、`pnpm typecheck` 均通过。
- Vitest：`8 files / 32 tests passed`。
- generated SDK 为生成产物，未手写重复 DTO 或新增内容库页面/feature API。

### 配置与脚本

- `docker compose --env-file .env.example config --quiet`：通过。
- `bash -n scripts/curl-file-smoke.sh`：通过。
- `git diff --check`：通过。

## 未覆盖与验证边界

- OpenSpec CLI 不存在，因此 strict validate 未执行。
- 尚未穷举：并发相同摘要、真实签名/会话过期、multipart 缺失分片、多 worker 竞争与进程重启恢复、401/403/404/管理员下载隔离全集、重试达到最大次数后的最终失败与人工重试。
- 故障探针覆盖“首次失败后恢复成功”，不等同于已覆盖最大重试最终失败矩阵。
- 本轮按用户要求不运行 Next.js build；没有前端业务页面，因此不运行 Playwright。
- 未实现病毒扫描，不得将类型/结构校验描述为病毒检测。

## 人工验收

- 待用户审核 PRD v0.6、OpenSpec、接口行为和上述未覆盖边界。
- 人工验收完成前保留对应 Tasks 未勾选；未经用户当轮授权不 commit、不 push。
