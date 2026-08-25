# Persistence Conventions Specification

## Requirement：公共字段按能力复用

SQLAlchemy 模型 SHALL 通过可组合 Mixin 复用 UUID 主键、创建/更新时间、创建/修改人和软删除字段；创建与更新、创建人与修改人 SHALL 能够按语义分别组合，业务模型 SHALL NOT 逐表重复声明相同公共字段。

### Scenario：普通可修改业务实体

- **WHEN** 模型需要主键、时间、操作人和软删除能力
- **THEN** 模型组合对应公共 Mixin
- **AND** 不在模型内重新声明同名公共列

### Scenario：追加式审计事件

- **WHEN** 模型语义为创建后不可修改的审计事件
- **THEN** 模型只组合主键能力，并使用领域字段 `occurred_at` 表达事件发生时间
- **AND** 不包含重复的 `created_at` 或无意义的 `updated_at`、`updated_by`、软删除字段

## Requirement：软删除查询安全

使用 Soft Delete Mixin 的业务模型 SHALL 在正常查询、RAG 检索和 Agent 上下文中默认排除 `deleted_at IS NOT NULL` 的记录。

### Scenario：查询已删除实体

- **WHEN** 普通业务查询涉及软删除模型
- **THEN** 已删除记录不出现在结果中
- **AND** 只有显式授权的管理或清理用例可以包含已删除记录

## Requirement：认证基线表约束

认证迁移 SHALL 创建 `users`、`auth_sessions`、`knowledge_bases` 和 `auth_audit_events`，并通过数据库约束保证用户名永久唯一、角色/状态合法、当前 Refresh 标识唯一和每个用户最多一个有效默认知识库。

### Scenario：并发注册同一用户名

- **WHEN** 两个事务并发注册规范化后相同的用户名
- **THEN** 数据库最多提交一个用户
- **AND** 另一个请求映射为 `AUTH_USERNAME_TAKEN`

### Scenario：创建第二个有效默认知识库

- **WHEN** 同一用户已经存在未删除的默认知识库，又尝试创建第二个未删除默认知识库
- **THEN** 数据库唯一约束拒绝该写入

## Requirement：注册事务完整性

用户、默认知识库、首个会话和注册成功审计 SHALL 在同一 PostgreSQL 事务内创建。

### Scenario：默认知识库创建失败

- **WHEN** 注册过程中默认知识库或会话写入失败
- **THEN** 用户和其他注册副作用全部回滚
- **AND** 系统不签发任何 Token

## Requirement：迁移不写入凭据

Alembic 迁移 SHALL 只创建 schema、约束和索引，不得创建测试用户、默认管理员或任何密码。

### Scenario：干净数据库迁移

- **WHEN** 对空测试数据库执行认证基线 upgrade
- **THEN** 所有认证表、约束和索引被创建
- **AND** 数据库中不存在迁移自动写入的用户或秘密
