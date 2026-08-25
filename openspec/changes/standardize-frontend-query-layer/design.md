# Design：统一前端 API 与 TanStack Query 数据访问层

## 依赖方向

```text
页面或组件
  -> feature queryOptions / mutationOptions
  -> feature API 函数
  -> 共享协议适配层
  -> OpenAPI 生成 SDK
  -> 后端
```

每个后端接口必须在对应 `src/features/<feature>/api.ts` 中封装一个纯异步函数。页面、组件、hooks、Query 配置和普通业务工具不得直接导入 `src/lib/api/generated`，也不得使用 `fetch` 绕过生成 SDK。

生成 SDK 是 OpenAPI 的只读产物，禁止手工修改。

## 成功响应

普通 query 解开 `{ code, message, data }` 后只返回业务 `data`。分页 query 返回：

```ts
type PageData<T> = {
  data: T[];
  meta: PageMeta;
};
```

mutation 返回：

```ts
type MutationResult<T> = {
  data: T;
  message: string;
};
```

适配层必须校验真实 HTTP 状态与响应体 `code` 一致，否则抛出契约异常。HTTP 204 不强制解包业务信封，由 mutation 配置提供默认成功消息。

## 统一错误

共享 `ApiError` 继承 `Error`，保留：

- `status`
- `code`
- `errorKey`
- `requestId`
- `validationErrors`
- `cause`

Problem Details、网络错误、非 JSON 错误和未知错误都转换为 `ApiError`。对外默认消息必须安全，不展示内部异常细节。`toFieldErrors()` 将 422 字段错误转换为与表单库无关的字段消息映射。

本轮只识别 401，不执行会话清理或页面跳转。

## TanStack Query

每个 feature 维护分层 query key 工厂，并通过 `queryOptions()` 或 `mutationOptions()` 定义缓存策略。组件不得散落 query key、SDK 调用或协议解包逻辑。

默认 query 重试规则：

- 4xx 与 500 不重试。
- 网络错误、502、503、504 最多重试两次。
- mutation 默认不重试。
- 健康检查保持 `retry: false`。

query 失败由页面错误态展示，不触发全局 Toast。

mutation meta 支持：

```ts
type AppMutationMeta = {
  successToast?: boolean | string;
  errorMode?: "global" | "local";
};
```

mutation 默认展示后端成功 `message`；可关闭或覆盖。普通错误默认全局提示一次；422 和 `errorMode: "local"` 交给页面处理。

## Toast

使用官方 shadcn Sonner 组件并在根布局挂载一个 Toaster。不得自行实现另一套 Toast。Toast 只承载跨业务 mutation 提示，不承载 query 轮询错误。

## 健康检查例外

健康检查是裸响应。`/ready` 的 HTTP 503 `ReadyResponse` 仍作为可展示的降级状态返回；其他 Problem Details 或网络错误转换为 `ApiError`。现有轮询频率与页面错误文案保持不变。

## 客户端边界

当前 TanStack Query 仅在浏览器客户端运行，统一使用 `/api/backend` 相对地址。本轮不预设服务端内网地址；未来引入 Server Component prefetch 时单独设计。

## 性能约束

QueryClient 使用惰性 state 初始化，保证每个客户端应用实例只创建一次。共享规则和 queryOptions 使用模块级纯函数，不通过 effect 或重复拦截器注册产生额外订阅。
