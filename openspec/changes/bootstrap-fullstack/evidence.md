# Evidence：全栈工程脚手架

验证日期：2026-08-24

## 已完成

- 根目录已初始化 Git，当前全部改动保持未提交，未配置远程仓库。
- `make init-env` 已生成被 Git 忽略的本地 `.env`，秘密值未输出。
- `make bootstrap-db` 已在既有 `myPostGres` 中创建 `xuemian_ai` 数据库与 `xuemian_ai_app` 用户；脚本为幂等实现。
- `make preflight` 已确认既有 PostgreSQL 与 Redis 容器正在运行并能正常响应。
- FastAPI OpenAPI 已导出至 `openapi/openapi.json`，前端 client 由 `@hey-api/openapi-ts` 生成。
- RustFS 使用官方 `1.0.0-rc.3` 标签与多架构 OCI index digest `sha256:800cf3f352a0a27e3275ca854a51f0027975d7acc7a0d52089a35bcc9fcbf0b5`；未使用 `latest`。
- shadcn/ui CLI 因官方初始化接口连接被对端关闭而未能自动初始化；仓库按 shadcn 代码所有权模式落地 `components.json`、Button 与 Badge，未引入替代 UI 库。

## 自动化证据

`make check` 通过：

- OpenAPI client 一致性检查
- Ruff format 与 lint
- mypy strict（14 个源码文件）
- Oxfmt
- Oxlint type-aware
- TypeScript `tsc --noEmit`
- `docker compose config --quiet`

`make test` 通过：

- 后端 pytest：3 passed
- 前端 Vitest：1 passed

## 明确未验证

- 按本期确认的验收边界，没有执行 `next build`、Docker image build 或整套 Compose 启动。
- RustFS、backend、frontend 容器的运行时 healthcheck 尚未实测，不能报告为已跑通。
- 没有创建 GitHub Actions，没有 commit 或 push。
