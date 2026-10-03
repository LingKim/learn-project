# Tasks：实现 AI 质量反馈与管理员诊断台

## 1. 规格与依赖

- [x] 更新 PRD 至 v0.8，定义“我要反馈”、管理员诊断台和单次请求授权边界
- [x] 完成 Proposal、Design 与两份增量 Specification
- [x] 确认 `implement-document-parsing-indexing` 已交付 `RetrievalTrace`、策略版本和消融 runner
- [x] 在首个真实 AI 结果页实施前确认 source type、结果引用和 `trace_id` 契约

## 2. 数据与权限

- [x] 创建 `AIQualityCase`、事件、授权、加密快照和回放记录 Alembic 迁移
- [x] 实现稳定工单号、活动工单幂等约束、状态机、乐观锁和保留/清理策略
- [x] 实现授权字段白名单、默认有效期、追加授权、拒绝、到期和撤销竞态
- [x] 实现逐字段正文读取门禁和管理员敏感访问审计

## 3. 用户反馈闭环

- [x] 实现创建、列表、详情、补充说明、授权决策、撤销和未领取撤回 API
- [x] 实现 source/trace/当前用户三重所有权校验和稳定错误码
- [ ] 在真实 AI 结果组件增加“我要反馈”入口、结构化类型、描述、期望结果和非默认勾选授权
- [ ] 实现用户工单列表、详情、状态时间线、公开回复和授权管理

## 4. 管理员诊断台

- [x] 实现脱敏概览、工单队列、筛选、领取/转交和状态转换 API
- [x] 实现工单详情、Trace 瀑布、候选排名对比、版本信息和访问审计 API
- [x] 实现追加授权请求、授权快照读取、公开回复和内部备注隔离
- [x] 实现隔离诊断回放和 FTS-only、Vector-only、Hybrid-only、无 Rerank、完整策略对比
- [ ] 实现管理员概览、列表、详情、回放和时间线页面，不提供正文导出、原文件下载或策略发布按钮

## 5. 契约与前端边界

- [ ] 后端真实 curl 权限矩阵通过后导出 OpenAPI 并重新生成只读前端 client
- [ ] 用户端和管理员端均通过 feature `api.ts`、query/mutation options 和共享协议层调用
- [ ] 增加边界检查，禁止页面直接 `fetch`、直接导入 generated SDK 或自行解释协议

## 6. 自动化与安全验证

- [x] 覆盖状态机、幂等、跨用户、跨工单、管理员角色、撤销/到期竞态和快照清理测试
- [x] 覆盖内部备注不出用户响应、正文不进日志/错误/指标、禁止导出/下载和浏览器缓存边界
- [x] 使用合成 Trace 验证故障阶段归因和五种消融回放，不使用真实用户正文
- [ ] 执行后端 curl、前端 Vitest 和隔离 Playwright 角色矩阵

## 7. 自审与交付

- [ ] 运行 Ruff、mypy、pytest、Oxfmt、Oxlint、TypeScript、Vitest、OpenAPI 和 API 边界检查
- [x] 更新 evidence，明确正文访问、回放隔离、清理和人工验收的真实验证边界
- [ ] 根据本轮用户授权由集成负责人执行适用构建和统一验证；本地提交已获授权，不 push、开 PR 或部署

## 2026-10-03 后端专项交付边界

- 已批准并实现的首期结果源为本人资料模式已成功且 `trace_complete=true` 的 LearningTurn；其他结果源未扩展。
- 上述已完成项为后端专项；迁移由集成负责人在独立分支创建并验证，前端页面、SDK 生成、完整真实服务 curl、调度器接线及统一验收仍由对应负责人继续完成。
- 后端专项 Ruff、mypy、pytest 已完成；第 7 节联合检查项包含前端工具，因此保留未完成直到统一验收。浏览器缓存边界目前由真实 HTTP `Cache-Control: no-store` 回归验证，未声称浏览器人工验收通过。
- 状态机还提供 `POST /ai-quality-cases/{case_id}/close`，以 `expected_version` 控制用户主动关闭或 resolved 后确认；未复用仅允许未领取撤回的 DELETE。
