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

浏览器请求 `/api/backend/*`，由 Next.js rewrite 同源转发至 FastAPI。`src/lib/api/generated/` 完全来自根目录 OpenAPI schema，不得手工修改。
