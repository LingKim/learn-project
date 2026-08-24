# 学面通AI

学面通AI是面向学习者与求职者的多模态 AI 学习与面试训练平台。当前仓库已完成全栈工程脚手架，尚未开始实现 PRD 业务里程碑。

## 技术基线

- 前端：Next.js、React、TypeScript、Tailwind CSS、shadcn/ui、TanStack Query、Oxlint、Oxfmt。
- 后端：Python 3.12、uv、FastAPI、SQLAlchemy、Alembic、LangChain、LangGraph。
- 本地基础设施：复用已运行的 PostgreSQL 与 Redis；Docker Compose 管理 RustFS、backend、frontend。

## 第一次使用

```bash
make init-env
make bootstrap-db
make install
```

`make init-env` 会生成只保存在本机且被 Git 忽略的 `.env`。`make bootstrap-db` 是唯一会修改现有 PostgreSQL 容器的入口：它幂等创建 `xuemian_ai` 数据库和 `xuemian_ai_app` 用户，不会删除或修改其他数据库。当前工作区已执行过这两步，重复执行不会覆盖 `.env`，也不会重复创建数据库。

## 开发命令

```bash
make dev             # 启动 frontend、backend、RustFS；可能触发首次镜像构建
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

详细产品基线见 `docs/学面通AI-产品需求文档.md`，本期规格见 `openspec/changes/bootstrap-fullstack/`。
