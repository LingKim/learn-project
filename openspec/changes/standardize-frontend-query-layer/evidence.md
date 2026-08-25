# Evidence：统一前端 API 与 TanStack Query 数据访问层

## 实现证据

- `frontend/src/lib/api/errors.ts`：统一 `ApiError`、Problem Details 转换、契约一致性和字段错误映射。
- `frontend/src/lib/api/protocol.ts`：统一普通响应、分页响应、mutation 与 HTTP 204 处理。
- `frontend/src/lib/query/`：统一 query 重试、mutation Toast 和 TanStack Query meta 类型。
- `frontend/src/features/system-health/api.ts`：唯一允许调用健康生成 SDK 的 feature API 边界。
- `frontend/src/features/system-health/queries.ts`：分层 query key 与 queryOptions。
- `frontend/scripts/check-api-boundaries.mjs`：拒绝组件和 Query 配置直接导入生成 SDK 或直接 `fetch`。
- `frontend/src/components/ui/sonner.tsx`：来自 shadcn 官方 `new-york-v4/sonner` registry 条目。

## shadcn CLI 证据

2026-08-25 先后执行：

```text
pnpm dlx shadcn@latest add sonner --yes
pnpm dlx shadcn@4.18.0 add sonner --yes
```

两次均在访问以下官方条目时失败：

```text
https://ui.shadcn.com/r/styles/new-york-v4/sonner.json
reason: other side closed
```

随后按前端规则直接读取同一官方 registry 条目，取得其原始 `sonner.tsx` 内容和依赖声明，并通过 `pnpm add sonner next-themes` 安装依赖：

```text
sonner 2.0.8
next-themes 0.4.6
```

未自行仿制 Toast 组件。

## 自动化验证

2026-08-25 实际执行 `pnpm check`：

```text
pnpm format:check
All matched files use the correct format.

pnpm lint
API 边界检查通过
Oxlint 通过

pnpm typecheck
TypeScript 通过

pnpm test
8 test files passed
33 tests passed

pnpm openapi:check
通过
```

额外执行：

```text
git diff --check
通过

pnpm openapi:generate
生成成功，生成目录最终无差异
```

## 覆盖场景

- Problem Details、网络错误、未知错误和错误状态不一致。
- 422 字段错误映射。
- 普通 query、分页 query、mutation、HTTP 204 和成功状态不一致。
- 4xx/500 不重试，网络错误及 502/503/504 最多重试两次。
- mutation 成功提示覆盖/关闭，422 与本地错误不重复提示。
- readiness 200、readiness 503 降级数据和 Problem Details。
- 健康 query key、轮询频率和禁用重试。
- 生成 SDK 非法导入和直接 fetch 门禁自检。

## 未执行项

- 当前环境未安装 `openspec` CLI，因此未执行 OpenSpec CLI validate；已人工核对目录、Requirement 与 Scenario 结构。
- 按约定未执行 Next.js build、Docker build、服务启动或浏览器端人工验收。
- 当前没有真实业务 mutation，因此全局 Sonner 行为由纯函数测试验证，未伪造业务接口。
- 未执行 Git commit 或 push。
