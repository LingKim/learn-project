# Design：双 JWT 认证、数据库与联调方案

## 1. 总体边界

```text
浏览器页面
  -> auth mutationOptions/queryOptions
  -> auth feature API
  -> OpenAPI 生成 SDK
  -> FastAPI auth router
  -> 注册/登录/刷新/查询/退出用例
  -> 用户、会话、知识库、审计持久化端口
  -> SQLAlchemy/PostgreSQL + Redis 限流适配器
```

后端是认证规则和接口契约的唯一事实源。FastAPI 路由只完成 HTTP、Cookie 和响应适配；密码验证、会话轮换、注册事务和重放处理位于应用用例；SQLAlchemy 与 Redis 细节留在基础设施适配器。

认证作为当前真实使用的业务模块创建，不预建其他空业务模块，也不建立全局巨型 `services.py`。

## 2. HTTP 接口

所有业务成功响应复用 `core.responses`，错误复用 RFC 9457 Problem Details 与现有项目异常体系。请求和响应模型进入 FastAPI OpenAPI，前端不得手写重复 DTO。

| 方法与路径 | 请求 | 成功行为 | 主要失败 |
| --- | --- | --- | --- |
| `POST /api/v1/auth/register` | `username`、`nickname`、`password` | 201；创建用户、默认知识库和会话，设置 Refresh Cookie，返回 Access Token 与当前用户 | 409 用户名占用；422 字段错误；429 限流；503 限流不可用 |
| `POST /api/v1/auth/login` | `username`、`password` | 200；创建独立设备会话，设置 Refresh Cookie，返回 Access Token 与当前用户 | 401 统一凭据错误；429 限流；503 限流不可用 |
| `POST /api/v1/auth/refresh` | 无正文；读取 Refresh Cookie | 200；原子轮换 Refresh Token，覆盖 Cookie，返回新 Access Token | 401 Token 无效、会话撤销或重放 |
| `GET /api/v1/auth/me` | Bearer Access Token | 200；返回当前用户 | 401 Token 或会话无效 |
| `POST /api/v1/auth/logout` | Refresh Cookie；可同时携带 Access Token | 200；幂等撤销当前会话并清除 Cookie | 无有效会话时仍清除 Cookie，不泄露状态 |

注册成功自动登录。当前用户只返回 `id`、`username`、`nickname`、`role` 和 `status`，不得返回密码哈希、Token 摘要或内部审计字段。

稳定 `error_key` 至少包括：

- `AUTH_INVALID_CREDENTIALS`
- `AUTH_ACCESS_TOKEN_INVALID`
- `AUTH_REFRESH_TOKEN_INVALID`
- `AUTH_SESSION_REVOKED`
- `AUTH_USERNAME_TAKEN`
- `AUTH_RATE_LIMITED`

429 响应必须携带 `Retry-After`。前端按 `error_key` 分支，不依赖中文 `message`。

## 3. 用户输入规则

- 用户名去除首尾空格并转为小写，长度 3～32，只允许小写字母、数字和下划线。
- 用户名全局永久唯一；软删除后仍不得复用。
- 昵称去除首尾空格，长度 1～40，允许中英文和常用符号，可以重复。
- 密码至少 8 位，并包含字母、数字、符号三类中的至少两类。
- 注册后账号立即为 `active`。

用户名规范化和密码规则必须由后端再次校验；前端即时校验只用于体验，不能成为安全边界。

## 4. 密码安全

密码使用 `pwdlib[argon2]` 的 Argon2id 哈希。应用不自行生成盐，不保存或记录明文密码。成功登录时若哈希参数已经落后于当前配置，则在同一安全流程中重新哈希并更新。

登录失败统一返回 `AUTH_INVALID_CREDENTIALS`，不得区分用户不存在、密码错误、账号软删除或账号禁用。注册冲突可以明确返回 `AUTH_USERNAME_TAKEN`。

## 5. JWT 与 Cookie

### 5.1 Access Token

- HS256，使用独立 Access Secret；密钥来自 Pydantic Settings，长度不足时应用拒绝启动。
- 绝对有效期 15 分钟。
- Claims：`sub`、`sid`、`role`、`type=access`、`iss`、`aud`、`iat`、`exp`、`jti`。
- 只由前端保存在内存，通过 `Authorization: Bearer` 发送，不进入 localStorage、sessionStorage 或普通 Cookie。

### 5.2 Refresh Token

- HS256，使用与 Access Token 不同的 Refresh Secret。
- 绝对有效期 7 天；轮换不会延长该会话的绝对到期时间。
- Claims：`sub`、`sid`、`family_id`、`type=refresh`、`iss`、`aud`、`iat`、`exp`、`jti`。
- Cookie 名 `xuemian_refresh_token`，`HttpOnly=true`、`SameSite=Lax`、`Path=/`；生产 `Secure=true`，本地开发允许 `false`。
- 数据库只保存当前 Refresh Token 的 HMAC-SHA256 摘要与 JTI，不保存明文 JWT。

Refresh 与 Logout 只接受 POST，并校验请求 `Origin` 是否属于配置白名单。CORS 仅允许明确来源且允许凭据，不使用 `*`。

## 6. 会话轮换与撤销

一次注册或登录创建一个独立 `auth_sessions` 记录和一个 Token 家族。允许多设备同时登录，普通 Logout 只撤销当前会话。

刷新时，以 `session_id + current_refresh_jti + current_refresh_digest + revoked_at IS NULL + expires_at` 作为条件执行原子更新：

1. 验签并校验 Refresh Token 类型、签发方、受众和时间。
2. 计算 Token 摘要并匹配当前会话。
3. 生成新 JTI 和新 Refresh Token，但保持原始绝对到期时间。
4. 条件更新恰好一行后提交并返回新 Token。
5. 条件未命中且签名 Token 指向既有家族时，视为旧 Token 重放，撤销整个家族并记录审计。

后端不设置并发刷新宽限窗口。前端 AuthProvider 使用全局 single-flight Promise，保证同一浏览器同时只有一次 Refresh 请求；等待者复用该结果。

每个受保护请求除 JWT 验签外，还必须确认用户为未删除的 `active` 状态，且 `sid` 对应会话未撤销、未过期。这样 Logout 后旧 Access Token 立即失效。

## 7. 数据库公共字段

SQLAlchemy 公共字段按能力拆为可组合 Mixin，业务模型不重复声明：

- `UuidPrimaryKeyMixin`：`id UUID`，默认 UUIDv4。
- `CreatedAtMixin` 与 `UpdatedAtMixin`：分别声明创建、更新时间；常规可修改实体通过组合的 `TimestampMixin` 同时复用两者。
- `CreatedByMixin` 与 `UpdatedByMixin`：分别声明创建、修改人；常规可审计实体通过组合的 `ActorAuditMixin` 同时复用两者。系统创建允许为空，外键删除不级联业务数据。
- `SoftDeleteMixin`：`deleted_at`、`deleted_by`，并提供统一的未删除查询约束。

Mixin 只组合真实需要的字段。追加式认证审计事件不使用 `updated_at`、`updated_by` 或软删除字段；纯关联表也不得为了形式统一携带无意义字段。Mixin 只负责字段和通用约束，不承载跨领域业务规则。

## 8. 表设计

```text
users 1 ─── * auth_sessions
  │
  ├─────── * knowledge_bases
  │
  └─────── * auth_audit_events（user_id 可空，用户软删除后仍保留）
```

### 8.1 `users`

组合主键、时间、操作人与软删除能力。

| 字段 | 约束与语义 |
| --- | --- |
| `id` | UUID 主键 |
| `username` | `VARCHAR(32)`，规范化值，全表唯一且软删除后不释放 |
| `nickname` | `VARCHAR(40)` |
| `password_hash` | `TEXT`，Argon2id 编码值 |
| `role` | `VARCHAR` + CHECK：`user`、`admin` |
| `status` | `VARCHAR` + CHECK：`active`、`disabled` |
| `last_login_at` | 可空；最近一次成功登录时间 |
| 公共字段 | `created_at`、`updated_at`、`created_by`、`updated_by`、`deleted_at`、`deleted_by` |

登录失败滚动计数不进入用户表，避免与 Redis 窗口状态产生双重事实源。

### 8.2 `auth_sessions`

组合主键与时间能力，不软删除。

| 字段 | 约束与语义 |
| --- | --- |
| `id` | UUID 主键，同时作为 JWT `sid` |
| `user_id` | 外键到用户，索引 |
| `family_id` | UUID，Token 家族，索引 |
| `current_refresh_jti` | UUID，当前 Token JTI，唯一 |
| `current_refresh_digest` | Token 的 HMAC-SHA256 摘要，唯一 |
| `absolute_expires_at` | 会话绝对到期时间 |
| `last_used_at` | 最近成功刷新时间 |
| `revoked_at` | 可空；撤销时间 |
| `revoke_reason` | 可空；固定原因码，不写自由文本凭据 |
| `ip_hash` | 可空；创建会话时的 IP 哈希 |
| `user_agent_summary` | 可空；长度受限的脱敏摘要 |

### 8.3 `knowledge_bases`

组合主键、时间、操作人与软删除能力。本轮只实现注册事务需要的最小记录：`owner_user_id`、`name`、`is_default` 及公共字段。部分唯一索引保证每个未删除用户最多一个未删除的默认知识库。

### 8.4 `auth_audit_events`

追加式表只复用 UUID 主键；事件发生时间使用有明确领域语义的 `occurred_at`，不增加重复的 `created_at`，也不包含 `updated_at`、操作人或软删除字段。其他字段为：`user_id` 可空、`username_fingerprint`、`event_type`、`outcome`、`reason_code`、`request_id`、`ip_hash`、`user_agent_summary`。不保存原始用户名、密码、JWT、Cookie、请求正文或异常原文。

审计记录不随用户软删除而删除，默认保留 180 天；后续清理任务物理删除到期事件。

## 9. 事务边界

- 注册：用户、默认知识库、首个会话与注册成功审计在同一事务；任何一步失败全部回滚，提交后才签发 Token。
- 登录成功：创建会话与成功审计在同一事务；需要升级密码哈希时一并更新。
- 登录失败：失败审计使用独立短事务，避免因认证失败回滚。
- Refresh：条件更新当前 Token 与刷新成功审计保持原子；重放撤销和重放审计保持原子。
- Logout：幂等写入 `revoked_at` 与原因码；无论会话是否已经失效，都清除浏览器 Cookie。

## 10. 限流

Redis 使用带环境前缀的 key，分别维护账号和 IP 的滑动窗口：

- 同一账号 15 分钟内失败 5 次，限制 15 分钟。
- 同一 IP 15 分钟内失败 20 次，限制 15 分钟。
- 登录成功清除该账号失败计数，不清除 IP 维度历史。
- 注册与登录调用原子 Redis 操作；Redis 不可用时返回 503，不绕过限流。
- Refresh、Me 和 Logout 不依赖登录限流，因此 Redis 限流故障不阻断已有会话。

## 11. 管理员初始化

提供显式 CLI 初始化命令，用户名和密码来自统一 Settings/命令输入，不提供默认值。命令在管理员不存在时以单事务创建管理员及默认知识库；重复执行不覆盖密码。同名普通用户存在时直接失败，不自动提升角色。命令与日志不得回显密码。

## 12. 前端联调

前端遵循既有数据访问方向：

```text
AuthProvider / 页面
  -> auth queryOptions / mutationOptions
  -> features/auth/api.ts
  -> 共享响应解包与 ApiError
  -> OpenAPI 生成 SDK
```

- 登录和注册成功后将 Access Token 写入内存，Refresh Token 由浏览器 Cookie 管理。
- AuthProvider 启动时先 Refresh，再调用 Me；完成前展示稳定加载态。
- Access Token 401 只触发一次 single-flight Refresh；重试仍失败则清空认证状态并跳转 `/login`。
- `/login`、`/register` 是公开路由；`/` 和后续业务路由默认受保护；已登录用户访问公开认证页时跳转 `/`。
- Access Token 通过生成 Client 支持的运行时认证配置注入，不修改生成代码，也不使用 Next Middleware 读取仅存在浏览器内存中的 Token。
- “记住账号”只在用户勾选时保存规范化用户名，不保存密码或 Token。
- 删除 `/first-login/change-password` 路由、表单、测试与所有导入。

## 13. 验证顺序

验证必须严格按以下阶段推进：

1. 后端单元测试：用户名/密码规则、JWT、摘要、错误映射和用例分支。
2. PostgreSQL/Redis 集成测试：迁移、约束、注册事务、限流、轮换竞态、重放与撤销。
3. 启动真实 FastAPI 服务，运行 `scripts/curl-auth-smoke.sh`；覆盖成功、冲突、错误凭据、未认证、刷新轮换、旧 Token 重放、Me、Logout 后失效和限流。
4. 只有 `curl` 全部通过后，导出 OpenAPI 并生成前端 Client。
5. 接入 feature API、TanStack Query 与 AuthProvider，完成组件/集成测试。
6. 使用 Playwright 在独立测试数据库和独立 Redis key 空间验证注册自动登录、退出、重新登录、刷新恢复、错误密码、限流提示、Refresh 轮换和撤销后跳转。

验收脚本使用临时用户名、临时 Cookie Jar 和临时 Token 文件，结束后清理；证据只记录状态码、错误码和脱敏断言，不记录真实密码或 Token。

## 14. 配置

认证配置统一进入 Pydantic Settings，至少包括 Access/Refresh Secret、issuer、audience、Token 时长、Cookie Secure、允许的 Origin、Refresh 摘要密钥、IP/用户名指纹密钥、Redis key 前缀和审计保留天数。`.env.example` 只提供变量名与安全生成说明，不提交真实秘密。
