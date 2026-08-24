# Frontend AI Coding 规则

- 使用 Next.js App Router、React、TypeScript strict、Tailwind CSS、shadcn/ui、TanStack Query。
- 默认使用 Server Component；只有交互、浏览器 API 或 TanStack Query 边界才添加 `"use client"`。
- API 类型和 client 由 `../openapi/openapi.json` 生成；禁止手写重复 DTO。
- 公共组件放 `src/components/ui`，业务代码按 `src/features/<feature>` 组织，不提前创建空模块。
- 视觉沿用象牙白、阳光黄、浅沙色、细描边、小圆角和轻阴影；禁止渐变、霓虹、玻璃拟态和卡片套卡片。
- 使用 Oxlint、Oxfmt、TypeScript、Vitest；禁止 ESLint、Prettier、Axios、Redux、Zustand。
- 默认不执行 `next build` 或 Docker build。
