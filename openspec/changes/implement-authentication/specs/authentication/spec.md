# Authentication Specification

## Requirement：开放注册并自动登录

系统 SHALL 接受规范化用户名、昵称和密码注册普通用户；用户名 SHALL 全局永久唯一。注册 SHALL 在同一事务创建用户、默认知识库、首个认证会话和成功审计，并在提交后签发双 JWT。

### Scenario：注册成功

- **WHEN** 未登录用户提交符合规则且未占用的用户名、昵称和密码
- **THEN** 系统返回 HTTP 201、Access Token 和当前用户
- **AND** 系统通过 `HttpOnly` Cookie 设置 Refresh Token
- **AND** 用户、默认知识库、会话和审计全部存在

### Scenario：用户名已占用

- **WHEN** 注册用户名与任意现存或软删除用户的规范化用户名相同
- **THEN** 系统返回 HTTP 409 和 `AUTH_USERNAME_TAKEN`
- **AND** 不创建任何部分数据

## Requirement：用户名密码登录

系统 SHALL 使用规范化用户名和 Argon2id 验证密码，成功后为当前设备创建独立会话。不存在、密码错误、禁用或软删除账号 SHALL 返回相同的凭据错误。

### Scenario：登录成功

- **WHEN** active 用户提交正确用户名和密码且未被限流
- **THEN** 系统返回 HTTP 200、Access Token 和当前用户
- **AND** 设置新的 Refresh Token Cookie

### Scenario：登录失败不枚举用户

- **WHEN** 用户名不存在、密码错误、账号禁用或账号已软删除
- **THEN** 系统返回 HTTP 401 和 `AUTH_INVALID_CREDENTIALS`
- **AND** 响应不得暴露具体失败原因

## Requirement：双 JWT 会话

系统 SHALL 签发 15 分钟 Access Token 和绝对 7 天 Refresh Token。Access Token SHALL 通过 Bearer Header 使用；Refresh Token SHALL 只通过 `HttpOnly` Cookie 使用并在每次刷新时轮换。

### Scenario：刷新成功

- **WHEN** 客户端提交签名有效、未过期、未撤销且与会话当前摘要匹配的 Refresh Token
- **THEN** 系统原子替换当前 Refresh JTI 和摘要
- **AND** 返回新 Access Token 并覆盖 Refresh Cookie
- **AND** 会话绝对到期时间不延长

### Scenario：旧 Refresh Token 重放

- **WHEN** 已轮换的旧 Refresh Token 被再次提交
- **THEN** 系统撤销对应 Token 家族
- **AND** 返回 HTTP 401 和稳定认证错误码
- **AND** 记录不含 Token 的重放审计事件

## Requirement：服务端可撤销会话

每个受保护请求 SHALL 同时验证 Access Token、用户状态和服务端会话状态。Logout SHALL 幂等撤销当前会话并清除 Refresh Cookie。

### Scenario：退出后使用旧 Access Token

- **WHEN** 用户退出后继续用该会话的未过期 Access Token 请求受保护接口
- **THEN** 系统返回 HTTP 401 和 `AUTH_SESSION_REVOKED`

### Scenario：重复退出

- **WHEN** 客户端对已经撤销或不存在的当前会话再次退出
- **THEN** 系统仍返回成功并清除 Refresh Cookie

## Requirement：认证限流

系统 SHALL 对注册和登录执行账号与 IP 双维度 Redis 限流；账号 15 分钟内登录失败 5 次或 IP 15 分钟内失败 20 次时限制 15 分钟。限流不可用时 SHALL NOT 绕过保护。

### Scenario：达到限流阈值

- **WHEN** 账号或 IP 达到失败阈值
- **THEN** 后续注册或登录返回 HTTP 429、`AUTH_RATE_LIMITED` 和 `Retry-After`
- **AND** 响应不说明命中了账号维度还是 IP 维度

### Scenario：Redis 限流不可用

- **WHEN** 注册或登录无法完成限流检查
- **THEN** 系统返回 HTTP 503
- **AND** 不执行认证或注册

## Requirement：认证隐私与审计

系统 SHALL 审计注册、登录成功、登录失败、刷新、重放和退出，但 SHALL NOT 保存或记录密码、JWT、Cookie、请求正文或原始异常消息。

### Scenario：登录失败审计

- **WHEN** 登录验证失败
- **THEN** 系统在独立短事务记录结果、稳定原因码、request ID、用户名指纹、IP 哈希和时间
- **AND** 审计记录不包含原始用户名或密码

## Requirement：不提供首次改密与密码重置

系统 SHALL NOT 提供首次登录强制改密、找回密码或管理员重置密码接口。

### Scenario：认证 OpenAPI 导出

- **WHEN** 导出本变更完成后的 OpenAPI
- **THEN** schema 包含注册、登录、刷新、Me 和 Logout
- **AND** 不包含首次改密、找回密码或管理员重置密码端点
