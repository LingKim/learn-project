# Engineering Foundation Specification

## Requirement：工程目录与治理

系统必须在单一根仓库内维护 `frontend/`、`backend/`、`docs/` 与 `openspec/`，并通过根级命令提供一致的安装、检查、测试和本地启动入口。

### Scenario：未经授权的 Git 操作

- **WHEN** AI 完成脚手架实现
- **THEN** 工作区可以存在未提交变更
- **AND** 不得自动 commit、push 或创建远程仓库

## Requirement：外部 PostgreSQL 与 Redis

本地运行必须复用宿主机已启动的 PostgreSQL 和 Redis，不得将其纳入本项目 Compose 生命周期。

### Scenario：backend 容器连接外部服务

- **WHEN** backend 在 Docker Desktop Compose 网络中运行
- **THEN** PostgreSQL 与 Redis 主机名使用 `host.docker.internal`
- **AND** 不得使用 `localhost` 或写死容器 IP

## Requirement：健康状态

后端必须分别提供存活与就绪端点，前端必须通过 TanStack Query 展示就绪状态。

### Scenario：依赖不可用

- **WHEN** 任一外部依赖不可达
- **THEN** `live` 仍返回成功
- **AND** `ready` 返回 HTTP 503
- **AND** 响应只包含逐项状态和安全错误码，不泄露凭据或连接串

## Requirement：API 契约

前端 TypeScript API client 必须从 FastAPI OpenAPI schema 生成，不得手工维护重复 DTO。

### Scenario：契约发生变化

- **WHEN** 后端 OpenAPI schema 更新
- **THEN** 生成命令可确定性更新前端 client
- **AND** 契约一致性检查能够发现未重新生成的差异

## Requirement：非 build 验收

本轮必须完成依赖锁定、格式检查、lint、类型检查、测试、OpenAPI 生成和 Compose 静态校验，但不得把未执行的应用 build 或容器启动报告为已通过。

