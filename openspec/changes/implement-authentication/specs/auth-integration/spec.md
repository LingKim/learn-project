# Authentication Integration Specification

## Requirement：curl 是前端联调准入门槛

系统 SHALL 在真实 FastAPI 服务上通过可重复执行的 `curl` 认证矩阵，之后才允许导出新 OpenAPI Client 并开始前端联调。

### Scenario：curl 存在失败场景

- **WHEN** 注册、冲突、登录、错误凭据、未认证、刷新、重放、Me、Logout 或限流任一场景未通过
- **THEN** 认证接口不得标记为可联调
- **AND** 不开始前端真实提交接入

### Scenario：curl 全部通过

- **WHEN** 完整矩阵在真实服务和独立测试数据上通过
- **THEN** 记录不含密码或 Token 的状态码、错误码和断言证据
- **AND** 才能导出 OpenAPI 并生成前端 Client

## Requirement：前端统一认证状态

前端 SHALL 通过 AuthProvider 在内存保存 Access Token，并在启动时先 Refresh、再 Me 恢复当前用户。并发 401 SHALL 共享一次 single-flight Refresh。

### Scenario：刷新页面恢复会话

- **WHEN** 浏览器仍有有效 Refresh Cookie 但内存 Access Token 已丢失
- **THEN** AuthProvider 刷新 Token 并查询当前用户
- **AND** 认证恢复完成前不错误闪现公开页或受保护内容

### Scenario：自动刷新失败

- **WHEN** Refresh 失败或刷新后重试仍返回 401
- **THEN** 前端清空认证状态并跳转登录页
- **AND** 不进行无限刷新循环

## Requirement：前端遵循生成契约与 Query 边界

认证页面 SHALL 通过 feature API、`queryOptions()` / `mutationOptions()`、共享响应解包与 `ApiError` 使用生成 SDK，不得直接调用 SDK、直接 `fetch` 业务接口或手写重复 DTO。

### Scenario：提交登录表单

- **WHEN** 用户提交通过前端校验的登录表单
- **THEN** 页面调用认证 mutation 配置
- **AND** mutation 经 feature API 和生成 SDK 请求后端

## Requirement：移除旧强制改密入口

前端 SHALL 删除 `/first-login/change-password` 页面、表单、测试和残留导入。

### Scenario：访问旧地址

- **WHEN** 浏览器访问旧首次改密地址
- **THEN** 不展示旧强制改密界面

## Requirement：真实浏览器 E2E

系统 SHALL 使用 Playwright 和隔离的 PostgreSQL/Redis 测试空间验证注册自动登录、退出、重新登录、刷新恢复、错误密码、限流提示、Refresh 轮换及撤销会话跳转。

### Scenario：E2E 测试执行

- **WHEN** 运行认证 E2E
- **THEN** 测试使用唯一用户名和独立测试配置
- **AND** 不重建、清空或污染日常开发使用的 PostgreSQL/Redis 数据
