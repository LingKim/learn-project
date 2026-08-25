# 学面通AI前端

Next.js App Router 前端脚手架。当前只有系统健康状态页，不包含 PRD 业务页面。

## 常用命令

```bash
pnpm install --frozen-lockfile
pnpm dev
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm openapi:check
```

## 数据访问约定

所有接口遵循以下依赖方向：

```text
组件 -> feature queries/mutations -> feature api.ts -> 共享 API 协议层 -> OpenAPI 生成 SDK
```

- 每个后端接口都必须封装 feature API 函数。
- 组件和 Query 配置不得直接导入 `src/lib/api/generated` 或直接 `fetch` 业务接口。
- 普通 query 返回业务 `data`，分页 query 返回 `{ data, meta }`。
- mutation 返回 `{ data, message }`，由全局 QueryClient 统一处理默认提示。
- 业务错误统一转换为 `ApiError`；422 可通过 `toFieldErrors()` 映射到具体表单。
- 使用 `pnpm boundaries:check` 验证 API 依赖边界。

浏览器请求 `/api/backend/*`，由 Next.js rewrite 同源转发至 FastAPI。`src/lib/api/generated/` 完全来自根目录 OpenAPI schema，不得手工修改。
