# Design：全栈工程脚手架

## 总体拓扑

```text
Browser
  -> Next.js :3000
  -> /api/backend/* rewrite
  -> FastAPI backend:8000/api/v1/*

FastAPI
  -> host.docker.internal:5432  PostgreSQL（外部）
  -> host.docker.internal:6379  Redis（外部）
  -> rustfs:9000                RustFS（Compose 内）
```

## 前端

- Next.js App Router、React、TypeScript strict、Tailwind CSS、shadcn/ui、TanStack Query。
- `features/system-health` 是本轮唯一功能模块；生成的 OpenAPI client 放入 `src/lib/api/generated`。
- 浏览器只访问 Next.js 同源地址；rewrite 负责透明转发，不在 Next.js 中重复实现后端业务。
- 使用 Oxlint、Oxfmt、TypeScript 和 Vitest，不安装 ESLint 或 Prettier。

## 后端

- Python 3.12、uv、FastAPI、Pydantic Settings、SQLAlchemy 2 async、Alembic、LangChain、LangGraph。
- 当前只建立 API、core 与 infrastructure 三个真实边界；未来业务按模块增量创建。
- `/api/v1/health/live` 只反映进程存活；`/api/v1/health/ready` 并行检查 PostgreSQL、Redis、RustFS。
- 错误使用 RFC 9457 Problem Details；请求链路使用 `request_id`；容器环境输出 JSON 日志。

## 外部依赖与秘密

- 本地 PostgreSQL、Redis 不属于 Compose 生命周期，不得由 `make dev` 或 `make down` 修改。
- backend 容器通过 `host.docker.internal` 访问宿主已发布端口，不写死容器 IP。
- `.env` 保存本地秘密且禁止进入 Git；`.env.example` 只包含无秘密占位符。
- RustFS 使用官方镜像并固定版本或 digest，使用命名卷持久化，不使用公开默认凭据。

## 失败行为

- PostgreSQL、Redis 或 RustFS 不可达时，`live` 仍可成功，`ready` 返回 503 和逐项脱敏状态。
- 不返回连接串、用户名、密码、内部异常堆栈或业务内容。
- OpenAPI 生成客户端与后端 schema 不一致时，质量检查失败。

