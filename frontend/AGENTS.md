# Frontend AI Coding 规则

- 使用 Next.js App Router、React、TypeScript strict、Tailwind CSS、shadcn/ui、TanStack Query。
- 默认使用 Server Component；只有交互、浏览器 API 或 TanStack Query 边界才添加 `"use client"`。
- API 类型和 client 由 `../openapi/openapi.json` 生成；禁止手写重复 DTO。
- 后续每个后端接口必须在对应 `src/features/<feature>/api.ts` 中封装纯异步 API 函数，并通过 feature 的 `queryOptions()` / `mutationOptions()` 供组件使用；页面、组件、hooks 和 Query 配置禁止直接导入 `src/lib/api/generated`、直接调用生成 SDK 或使用 `fetch` 绕过 API 层。
- 业务 API 必须复用 `src/lib/api` 的统一响应解包与 `ApiError`，Query Key 必须由 feature 分层工厂维护；query 错误由页面展示，mutation 提示遵循全局 meta 规则，禁止自行建立另一套协议处理或全局提示机制。
- 公共组件放 `src/components/ui`，业务代码按 `src/features/<feature>` 组织，不提前创建空模块。
- 项目已安装的组件库和图标库能满足需求时必须优先复用，禁止无必要手写；确需自行实现的 `Input` 等基础控件必须先封装为 `src/components/ui` 下的公共组件，不得散落在业务页面或功能组件中。
- `components.json` 只代表已配置 shadcn/ui，不代表全部组件已经落盘；shadcn 官方 registry 已提供的组件必须先通过 `pnpm dlx shadcn@latest add <component>` 添加并复用，禁止自行复刻。CLI 因网络或工具故障不可用时，只能在记录失败证据后使用同一官方 registry 返回的原始源码；只有 registry 不提供或经确认存在依赖/兼容性限制时才允许手写，并须在 OpenSpec 中记录理由。
- 视觉沿用象牙白、阳光黄、浅沙色、细描边、小圆角和轻阴影；禁止渐变、霓虹、玻璃拟态和卡片套卡片。
- 使用 Oxlint、Oxfmt、TypeScript、Vitest；禁止 ESLint、Prettier、Axios、Redux、Zustand。
- 默认不执行 `next build` 或 Docker build。
