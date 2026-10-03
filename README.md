# 学面通AI

学面通AI是面向学习者与求职者的多模态 AI 学习与面试训练平台。当前已实现认证、个人资料、内容库与文件管理。文档解析、页面 OCR、索引及受保护检索已实现并部署到本机开发环境，学习快速回答已接入 `qwen3.8-flash`，支持资料/通用模式、中文/英文回答、引用预览、追问、私有历史、重命名、软删除和反馈。快速回答入口为 `/learning`。刷题练习第一版已实现并在本机运行，待人工验收，入口为 `/learning/practice`，支持五种题型、配置确认、题集版本、逐题点评和私有练习历史；实际验收状态见本期 evidence。

## 技术基线

- 前端：Next.js、React、TypeScript、Tailwind CSS、shadcn/ui、TanStack Query、Oxlint、Oxfmt。
- 后端：Python 3.12、uv、FastAPI、SQLAlchemy、Alembic、LangChain、LangGraph、LlamaIndex。
- 本地基础设施：复用已运行的 PostgreSQL 与 Redis；Docker Compose 管理 RustFS、Qdrant、backend、document-worker、practice-worker、frontend。

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

本次没有运行 Next.js / Docker build，也没有执行 Git commit / push。功能测试、真实模型质量、浏览器和人工验收须分别查阅 evidence，运行状态不代表全部验收通过。
