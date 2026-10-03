# 学面通AI

学面通AI是面向学习者与求职者的多模态 AI 学习与面试训练平台。当前已实现认证、个人资料、内容库与文件管理。文档解析、页面 OCR、索引及受保护检索已实现并部署到本机开发环境，学习快速回答已接入 `qwen3.8-flash`，支持资料/通用模式、中文/英文回答、引用预览、追问、私有历史、重命名、软删除和反馈。快速回答入口为 `/learning`。刷题练习第一版已实现并在本机运行，待人工验收，入口为 `/learning/practice`，支持五种题型、配置确认、题集版本、逐题点评和私有练习历史；实际验收状态见本期 evidence。难点资产与文字知识精讲第一版已实现并在本机运行，入口为 `/weaknesses` 与 `/learning/explanation`，支持评分证据、手动难点、五部分卡片、持久任务和针对性再练；用户人工验收待完成。

## 技术基线

- 前端：Next.js、React、TypeScript、Tailwind CSS、shadcn/ui、TanStack Query、Oxlint、Oxfmt。
- 后端：Python 3.12、uv、FastAPI、SQLAlchemy、Alembic、LangChain、LangGraph、LlamaIndex。
- 本地基础设施：复用已运行的 PostgreSQL 与 Redis；Docker Compose 管理 RustFS、Qdrant、backend、document-worker、practice-worker、knowledge-worker、frontend。

## 第一次使用

```bash
make init-env
make bootstrap-db
make install
```

`make init-env` 会生成只保存在本机且被 Git 忽略的 `.env`。`make bootstrap-db` 是唯一会修改现有 PostgreSQL 容器的入口：它幂等创建 `xuemian_ai` 数据库和 `xuemian_ai_app` 用户，不会删除或修改其他数据库。当前工作区已执行过这两步，重复执行不会覆盖 `.env`，也不会重复创建数据库。

## 开发命令

```bash
make dev             # 启动 frontend、backend、RustFS、Qdrant、worker；可能触发首次镜像构建
make practice-worker # 本机运行持久化练习任务 worker
make knowledge-worker # 本机运行精讲任务与难点评分事件 worker
make down            # 只停止本项目管理的服务
make contract        # 校验 OpenAPI 与生成 client 一致
make check           # 非 build 静态质量门禁
make test            # 前后端测试
make compose-config  # 静态验证 Compose
```

本机外部依赖必须先保持运行：

```text
PostgreSQL  localhost:5432
Redis       localhost:6379
```

`make dev` 会先运行只读 preflight，确认这两个容器处于运行状态并能响应；失败时明确退出。Compose 内的 backend 通过 `host.docker.internal` 访问它们，本项目不会启动、停止或重建这两个容器。

## 当前接口

- `GET /api/v1/health/live`：FastAPI 进程存活。
- `GET /api/v1/health/ready`：并行检查 PostgreSQL、Redis、RustFS。
- 前端通过 `/api/backend/*` 同源转发访问 FastAPI。

详细产品基线见 `docs/学面通AI-产品需求文档.md`，本期规格与验证记录见 `openspec/changes/implement-document-parsing-indexing/`。

文档解析部署步骤和资源限制见 `backend/README.md`。2026-10-02 已按用户授权将本机 `xuemian_ai` 迁移到 `20261002_01`，初始化正式 Qdrant collection，并启动本机 API、前端及 worker。访问 `http://127.0.0.1:3000`。PostgreSQL/Redis/RustFS/Qdrant 在 Docker；前后端与 worker 使用本机源码开发进程，PID/日志保存在被 Git 忽略的 `.runtime/`。这不是生产镜像部署，机器重启后本机进程需要重新启动。

## 刷题练习

规格与进度：`openspec/changes/implement-learning-practice/`。本机业务库已备份并升级至 `20261003_03`，API / practice-worker 已启动，PID 与日志记录在 `.runtime/processes.json`。备份为 `.runtime/backups/xuemian_ai-before-practice-20261003T044233Z.dump`，已验证备份目录可读取。

模型操作持久化返回 HTTP 202，页面通过任务编号读取状态。practice-worker 默认并发 2、30 秒租约与 180 秒任务上限，可通过 `.env.example` 的 `PRACTICE_*` Settings 调整；worker 重启可继续 pending，processing 租约过期后必须明确重试。后端是评分与业务规则唯一事实源；本期为非限时练习，文本编程题不执行代码。

开发验收阶段没有运行 Next.js / Docker build；Git 交付按用户当轮明确授权执行。功能测试、真实模型质量、浏览器和人工验收须分别查阅 evidence，运行状态不代表全部验收通过。

## 难点资产与文字精讲

规格与验收：`openspec/changes/implement-learning-assets/`。本机业务库已备份并迁移至 `20261003_04`，现有资料/练习 worker 保持运行，并新增 knowledge-worker。备份为 `.runtime/backups/xuemian_ai-before-20261003_04-20261003T071137Z.dump`，受管进程与日志见 `.runtime/processes.json`。

难点使用本人评分与版本证据，候选需确认或符合重复错误门槛；手动创建是用户主动学习声明。掌握状态由用户操作，针对性练习按全部相关题的提交、评分、正确数与低置信度计算验证结论，不自动标记已掌握。旧卡片不可变，刷新可恢复当前任务，取消或失败保留旧结果。

knowledge-worker 默认并发 2、30 秒租约、180 秒任务上限；`KNOWLEDGE_*` 配置见 `.env.example`。资料精讲先受保护检索，再生成和逐字段依据审计，不支持或证据不足的内容不发布；通用精讲明确标注模型通用知识。真实六格式合成评测本轮为 3 份接受、3 份因额外保证被拦截，不代表自然资料的整体准确率。自动化、语义复核、浏览器和用户人工验收分别记录在 evidence。


## 2026-10-03 并行可靠性修复与下一批开发

本轮在三份功能worktree并行修复既有学习行为，再整合至独立 `codex/learn-integration-20261003`：失败重试约束、来源恢复复习版本、答案保存/提交、任务恢复/迟到响应、失效原文缓存和会话间私有缓存隔离。完整提交与验证见 `openspec/changes/fix-learning-workflow-reliability/`。修复尚未合入main或更新本机运行进程，不把构建成功当作部署。

下一批质量诊断台与提示词管理的待批准最小范围、公共契约、文件归属和验收条件见 `docs/development/parallel-next-batch-20261003.md`。须先冻结真实结果/Trace与Prompt运行版本契约，再分开后端与前端worktree实施；本轮只交付具体方案，没有新增这两套功能。
