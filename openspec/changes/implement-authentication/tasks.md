# Tasks：实现认证闭环并完成前后端联调

## 1. 规格与数据库

- [x] 通过分轮决策树确认功能范围、双 JWT、数据库、限流、curl 与 E2E 边界
- [x] 更新 PRD，删除首次强制改密、管理员重置密码和验证码冲突
- [x] 编写认证 Proposal、Design 与增量 Specification
- [x] 建立可组合 SQLAlchemy 主键、时间、操作人和软删除 Mixin，并增加模型结构测试
- [x] 创建用户、会话、默认知识库和认证审计模型及约束
- [x] 创建 Alembic 认证基线迁移，验证干净数据库 upgrade/downgrade/upgrade

## 2. 后端认证

- [x] 通过 `uv add` 引入 Argon2id 与 JWT 依赖，更新锁文件
- [x] 增加认证 Settings 与启动期秘密强度校验，更新 `.env.example`
- [x] 实现用户名规范化、密码校验与 Argon2id 哈希/自动升级
- [x] 实现注册事务、登录、Refresh 原子轮换与重放撤销、Me 和幂等 Logout 用例
- [x] 实现账号/IP Redis 限流及 Redis 故障时 503 行为
- [x] 实现认证路由、Cookie/Origin/CORS 适配、Bearer 认证依赖和稳定 `error_key`
- [x] 实现幂等管理员初始化命令，不回显或覆盖密码
- [x] 增加单元测试和真实 PostgreSQL/Redis 集成测试

## 3. curl 准入门禁

- [x] 创建不包含固定凭据的 `scripts/curl-auth-smoke.sh`
- [x] 启动真实后端并验证注册、冲突、登录、错误凭据、未认证、Refresh 轮换、重放、Me、Logout 和限流矩阵
- [x] 清理临时 Cookie/Token/测试用户，并将脱敏结果写入 evidence
- [x] curl 矩阵未全部通过时停止，不生成前端 Client、不开始联调

## 4. 前端联调

- [x] 在 curl 门禁通过后导出 OpenAPI 并重新生成前端 Client
- [x] 删除首次强制改密路由、表单、测试和残留导入
- [x] 按 feature API 与 mutation/query options 规范接入注册、登录、Refresh、Me 和 Logout
- [x] 实现内存 Access Token、single-flight Refresh、AuthProvider 与公开/受保护路由行为
- [x] 实现“记住账号”仅保存用户名以及稳定错误码到中文提示的映射
- [x] 增加前端单元、组件和认证状态集成测试

## 5. E2E 与交付验证

- [x] 建立 Playwright 配置、独立测试数据库和独立 Redis key 空间
- [x] 覆盖注册自动登录、退出、重新登录、刷新恢复、错误密码、限流、Refresh 轮换和撤销跳转
- [x] 执行 Ruff、mypy、pytest、Alembic、Oxfmt、Oxlint、TypeScript、Vitest、OpenAPI 一致性与 Playwright 验证
- [x] 自审安全日志、秘密、测试隔离、OpenSpec 任务状态和实际 evidence
- [ ] 交由用户进行人工验收；未经当轮授权不 commit、不 push
