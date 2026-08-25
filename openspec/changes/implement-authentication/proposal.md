# Proposal：实现认证闭环并完成前后端联调

## 背景

前端已经具备登录和注册页面，但当前表单只进行本地校验，FastAPI 只有健康检查接口，数据库也没有用户或会话表。最新产品决策取消首次登录强制改密与管理员重置密码，认证采用 Access Token + Refresh Token 双 JWT。

本变更需要先建立后端认证、数据库和安全边界，以真实 `curl` 验证作为前端联调的强制准入门槛，最终通过 Playwright 验证浏览器中的完整会话生命周期。

## 目标

- 实现注册自动登录、登录、Refresh 轮换、当前用户和退出五个接口。
- 使用 PostgreSQL 持久化用户、可撤销会话、默认知识库和认证审计事件，Redis 承担注册/登录限流。
- 通过可组合 SQLAlchemy Mixin 复用主键、时间、操作人和软删除公共字段。
- 使用 Argon2id 保存密码，使用双 JWT、`HttpOnly` Refresh Cookie 和 Token 家族重放检测保护会话。
- 在真实服务上完成可重复的 `curl` 正反向矩阵，通过后才生成前端 Client 并进行联调。
- 按现有 feature API、TanStack Query 和共享 `ApiError` 规范接入前端，并建立 Playwright E2E 基线。

## 范围

- FastAPI 认证模块、应用用例、持久化适配器、认证依赖和配置。
- `users`、`auth_sessions`、`knowledge_bases`、`auth_audit_events` 及 Alembic 迁移。
- 幂等管理员初始化命令。
- OpenAPI 导出、前端 Client 生成、认证 feature API、mutation/query options、全局认证状态和路由保护。
- 首次改密旧页面、表单和测试的删除。
- 后端单元/集成测试、真实 `curl` 验收脚本和 Playwright E2E。

## 非目标

- 不实现首次强制改密、普通修改密码、找回密码、管理员重置密码或全部设备退出。
- 不实现管理员用户管理接口或管理后台联调。
- 不实现知识库文档、分块、向量、解析或检索能力，只创建注册事务真实需要的最小默认知识库记录。
- 不引入验证码、邮箱、手机号、OAuth、第三方身份平台或微服务拆分。
- 不由 Compose 启动、停止、重建或删除本机 PostgreSQL 与 Redis。
- 不执行 Next.js build 或 Docker image build，除非用户另行明确授权。

## 风险

- Refresh Token 轮换若缺少原子条件更新，会出现并发刷新和重放检测竞态；后端使用数据库条件更新，前端使用 single-flight 刷新锁。
- Access Token 若只做无状态验签，退出后仍可使用至过期；受保护请求必须同时校验用户与服务端会话状态。
- Refresh Cookie 经 Next.js rewrite 与直接 `curl` 访问的路径不同；Cookie 使用 `Path=/`，并通过 Origin 白名单、`SameSite=Lax` 和只接受 POST 降低 CSRF 风险。
- 测试若复用日常数据库可能污染用户数据；集成与 E2E 必须使用独立测试数据库和独立 Redis key 空间。
- Redis 故障时放行会绕过防暴力破解；注册与登录在限流不可用时安全失败为 503。

## 验收证据

- Alembic 在干净测试数据库完成 upgrade/downgrade/upgrade，表、约束和索引符合设计。
- Ruff、mypy、pytest 通过，包含真实 PostgreSQL/Redis 集成测试。
- 真实启动的 FastAPI 服务通过完整 `curl` 认证矩阵，结果记录在本变更 evidence 中且不包含 Token 或密码。
- `curl` 门禁通过后导出 OpenAPI、生成前端 Client，并通过 OpenAPI 一致性与前端架构边界检查。
- 前端 Oxfmt、Oxlint、TypeScript、Vitest 与 Playwright E2E 通过。
- 按项目规则不以文件存在、配置写入或 Mock 成功冒充真实服务与端到端验证。
