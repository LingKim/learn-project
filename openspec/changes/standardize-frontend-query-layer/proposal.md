# Proposal：统一前端 API 与 TanStack Query 数据访问层

## 背景

后端已统一业务成功响应和 RFC 9457 错误响应，但前端当前只有健康检查一个真实 query，并在 feature API 中手工判断生成 SDK 的 `data/error`。该实现会丢失状态码、`error_key`、`request_id` 和字段校验详情，也没有统一的重试、mutation 提示和依赖边界。

## 目标

- 在 OpenAPI 生成 SDK 与业务 feature 之间建立统一协议适配层。
- 每个接口必须经过 feature API 函数，禁止页面和 Query 配置直接调用生成 SDK或业务 `fetch`。
- 统一成功解包、分页解包、204、Problem Details、网络异常和未知异常。
- 统一 QueryClient 重试与 mutation 提示策略，同时保留页面级错误处理能力。
- 将现有健康查询迁移到 `feature API -> queryOptions -> component` 链路。

## 范围

- `src/lib/api/` 下的共享协议、错误和重试能力。
- QueryClient 默认策略及 mutation 全局提示。
- 官方 shadcn Sonner 组件与根布局挂载。
- 系统健康 feature 的 API、query key 和 queryOptions 迁移。
- 静态架构门禁、测试、文档和前端规则。

## 非目标

- 不创建尚不存在的认证或业务 API。
- 不实现 401 自动注销或登录跳转。
- 不设计 SSR/Server Component API 地址。
- 不修改 OpenAPI 生成目录中的源码。
- 不运行 Next.js build 或 Docker build。

## 风险

- 全局 query Toast 会在轮询和多订阅场景重复出现；query 错误只进入页面错误态。
- mutation 全局提示可能与页面提示重复；通过 mutation meta 提供关闭、覆盖和本地处理能力。
- readiness 503 是可展示的降级数据；继续保留端点级特例。
- 生成 SDK 返回未知错误形态；统一适配层必须使用运行时类型守卫，不以宽泛断言掩盖契约缺口。

## 验收证据

- 协议解包、错误规范化、字段错误映射和重试策略单元测试。
- 健康检查 queryOptions 与 readiness 503 回归测试。
- 架构门禁能够拒绝组件或 Query 配置直接导入生成 SDK。
- Oxfmt、Oxlint、TypeScript、Vitest 和 OpenAPI client 一致性检查结果。
