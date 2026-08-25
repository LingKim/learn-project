# 学面通AI：AI Coding 规则

## 工作方式

- 所有业务与工程变更遵循 `PRD -> OpenSpec -> 实现 -> 自审 -> 自动化验证 -> 人工验收`。
- 非平凡变更必须先更新 `openspec/`，不得直接从一句需求跳到实现。
- 代码、测试、迁移脚本和配置均由 AI 创建与维护；用户负责产品决策和结果验收。
- 未经用户当轮明确授权，不得执行 Git commit、push、创建远程仓库或提交 PR。
- 修改代码后默认不执行 build；只有用户明确要求时才运行 Next.js build 或 Docker image build。

## 架构边界

- `frontend/` 是 Next.js 前端；`backend/` 是 FastAPI 后端；后端是接口与业务规则的唯一事实源。
- 前后端契约来自 FastAPI OpenAPI；禁止手写一套与后端重复的 TypeScript DTO。
- 后续前端对接任何后端接口都必须遵循 `frontend/AGENTS.md` 的统一数据访问规范：经 feature API、`queryOptions()` / `mutationOptions()`、共享响应解包与 `ApiError` 接入，禁止页面或组件直接调用生成 SDK、直接 `fetch` 业务接口或另建协议处理层。
- 后端采用模块化单体。只创建当前真实使用的模块，不预建空业务目录。
- 本地 PostgreSQL 和 Redis 是外部依赖，本项目不得自动启动、停止、重建或删除它们。
- 用户业务数据、凭据和模型密钥不得写入 Git、日志或面向管理员的业务界面。

## 质量要求

- 前端使用 Oxlint、Oxfmt、TypeScript 和 Vitest；禁止引入 ESLint、Prettier。
- 后端使用 Ruff、mypy 和 pytest。
- 每次实现必须同步测试、文档和 OpenSpec 任务状态，并报告实际验证结果与未验证项。
- 不得用“文件存在”“配置已写”冒充服务已启动或端到端已跑通。
