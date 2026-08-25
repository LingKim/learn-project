# Evidence：认证闭环并完成前后端联调

## 交付状态

截至 2026-08-25，数据库设计、后端认证、真实 curl 门禁、OpenAPI Client、前端联调与 Playwright E2E 已完成。仅保留用户人工验收；本轮未执行 Git commit、push、Next.js build 或 Docker image build。

## 数据库与后端实现

- `persistence/mixins.py` 按能力提供 UUID 主键、创建/修改时间、创建/修改人和软删除 Mixin；认证审计事件只组合真实需要的主键能力。
- Alembic `20260825_01_authentication_baseline.py` 创建 `users`、`auth_sessions`、`knowledge_bases`、`auth_audit_events` 及约束、索引和外键。
- 认证实现使用 Argon2id、Access/Refresh 双 JWT、Refresh 摘要、PostgreSQL 可撤销会话、旧 Token 重放撤销家族、Redis 账号/IP 限流、Origin/CORS 与 `HttpOnly` Cookie。
- 暴露 `register`、`login`、`refresh`、`me`、`logout` 五个接口；首次强制改密、管理员重置密码、找回密码和验证码不在本期范围。
- 干净数据库执行 `alembic upgrade head -> downgrade base -> upgrade head` 通过，最终 revision 为 `20260825_01 (head)`。

## curl 准入门禁

真实 FastAPI、PostgreSQL 与 Redis 环境执行 `scripts/curl-auth-smoke.sh`，在生成前端 Client 和开始联调前全部通过：

```text
register 201
duplicate username 409 / AUTH_USERNAME_TAKEN
me 200
unauthenticated me 401 / AUTH_ACCESS_TOKEN_INVALID
refresh rotation 200
old refresh replay 401 / AUTH_REFRESH_TOKEN_INVALID
replay revoked family 401
login 200
invalid credentials 401 / AUTH_INVALID_CREDENTIALS
logout 200
revoked access 401 / AUTH_SESSION_REVOKED
account rate limit 429 / AUTH_RATE_LIMITED
```

临时 Cookie Jar 与 Token 文件由脚本 trap 删除；本次两个随机测试账号、关联会话、知识库和审计已从测试数据中精确清理。证据未记录明文密码、JWT、Cookie 或秘密配置。

## 前端联调

- curl 门禁通过后重新导出 `openapi/openapi.json` 并生成 `frontend/src/lib/api/generated/`。
- 认证调用经 `features/auth/api.ts` 和 `mutationOptions()` 进入生成 Client，复用共享响应解包与 `ApiError`。
- AuthProvider 只在内存保存 Access Token；Refresh Token 由浏览器 `HttpOnly` Cookie 管理；启动时以 single-flight Refresh 后调用 Me 恢复会话。
- `/` 受保护，`/login` 与 `/register` 为公开认证页；退出后返回登录页。记住账号只使用版本化 localStorage key 保存规范化用户名。
- 已删除 `/first-login/change-password` 页面、表单、测试和残留引用。

## 自动化验证

后端：

```text
uv run ruff format --check .  通过
uv run ruff check .           通过
uv run mypy                   通过
uv run pytest                 44 passed
uv run alembic current        20260825_01 (head)
```

前端：

```text
pnpm format:check             通过
pnpm lint                     通过，API 边界检查通过
pnpm typecheck                通过
pnpm test                     8 files / 32 tests passed
pnpm openapi:check            通过
```

Playwright：

```text
pnpm test:e2e                 4 passed
```

E2E 每次使用独立的 `${APP_DB_NAME}_e2e` 数据库、唯一 `AUTH_REDIS_KEY_PREFIX`、后端 `8100` 端口和前端 `3100` 端口；运行前迁移并清空隔离认证表，退出 trap 再次清理认证表和该次 Redis keys。覆盖：

- 未登录访问首页跳转登录；
- 注册自动登录和页面刷新恢复；
- 退出、错误密码提示、正确密码重登；
- Refresh 轮换、旧 Token 重放、家族撤销后跳转登录；
- 五次错误密码后的 429 中文提示；
- 已取消的首次改密路由返回 404。

运行结束后只读复核：`users`、`auth_sessions`、`knowledge_bases`、`auth_audit_events` 均为 0 行，E2E Redis key 数为 0，`3100` 与 `8100` 端口均已停止监听。

## 未执行与人工验收

- 按项目规则未运行 `next build` 或 Docker image build。
- 未执行 Git commit、push 或创建 PR。
- 等待用户在本地人工验收登录、注册、刷新恢复和退出体验。
