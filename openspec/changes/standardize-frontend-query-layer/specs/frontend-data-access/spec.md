# Frontend Data Access Specification

## Requirement：Feature API 是接口访问边界

每个后端接口必须由对应 feature 的 API 函数封装。页面、组件、hooks 和 Query 配置不得直接调用 OpenAPI 生成 SDK 或业务 `fetch`。

### Scenario：组件加载业务数据

- **WHEN** 组件需要调用后端接口
- **THEN** 组件使用 feature 提供的 queryOptions 或 mutationOptions
- **AND** Query 配置调用 feature API 函数
- **AND** 只有 feature API 与共享协议层可以接触生成 SDK

### Scenario：违反导入边界

- **WHEN** 页面、组件或 Query 配置直接导入生成 SDK
- **THEN** 静态质量检查必须失败

## Requirement：统一成功数据处理

普通 query 必须向组件返回业务 `data`，分页 query 必须返回 `data` 与 `meta`，mutation 必须保留业务 `data` 和成功 `message`。

### Scenario：响应状态一致

- **WHEN** SDK 返回业务成功信封
- **THEN** 适配层校验真实 HTTP 状态与响应体 `code` 一致
- **AND** 返回调用方所需的解包数据

### Scenario：响应状态不一致

- **WHEN** HTTP 状态与响应体 `code` 不一致
- **THEN** 适配层抛出统一契约异常

### Scenario：HTTP 204

- **WHEN** mutation 成功但没有响应正文
- **THEN** 不强制解析业务信封
- **AND** mutation 配置可以提供默认成功消息

## Requirement：统一前端错误

后端 Problem Details、网络错误、非 JSON 错误和未知错误必须转换为 `ApiError`，并保留安全提示与可操作的结构化信息。

### Scenario：422 参数校验失败

- **WHEN** Problem Details 包含字段级 errors
- **THEN** `ApiError` 保留校验详情
- **AND** 公共函数可以转换为表单字段消息映射
- **AND** 默认不重复展示全局错误 Toast

### Scenario：401 未认证

- **WHEN** 后端返回 401
- **THEN** `ApiError` 正确保留 401 状态
- **AND** 本轮不得自动清理会话或跳转

## Requirement：统一 TanStack Query 策略

QueryClient 必须集中维护跨业务重试和 mutation 提示策略；feature 必须维护分层 query key 与 queryOptions/mutationOptions。

### Scenario：可恢复 query 错误

- **WHEN** query 发生网络错误或 502、503、504
- **THEN** 最多自动重试两次

### Scenario：不可恢复 query 错误

- **WHEN** query 发生 4xx 或 500
- **THEN** 不自动重试

### Scenario：mutation 成功

- **WHEN** mutation 返回后端成功消息且未关闭提示
- **THEN** 全局只展示一次成功 Toast
- **AND** mutation meta 可以关闭或覆盖消息

### Scenario：mutation 本地错误处理

- **WHEN** 错误是 422 或 mutation meta 指定 local
- **THEN** 全局不得重复展示错误 Toast

## Requirement：健康检查保持专用语义

系统健康 query 必须通过 feature API 和 queryOptions 调用，同时保留 readiness 503 的降级数据语义。

### Scenario：依赖降级

- **WHEN** readiness 返回 HTTP 503 和 `ReadyResponse`
- **THEN** query 以成功数据状态向页面提供降级检查结果
- **AND** 页面继续展示具体不可用依赖

### Scenario：健康接口返回 Problem Details

- **WHEN** readiness 返回非降级的标准错误
- **THEN** feature API 抛出统一 `ApiError`
