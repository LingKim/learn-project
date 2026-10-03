# 前端实现与验证记录

2026-10-03，用户批准后实施。业务接口和类型来自本轮真实 FastAPI OpenAPI 生成 SDK；本 feature 仅在 api.ts 导入生成 SDK/types，页面经 queryOptions/mutationOptions 与共享 ApiError/响应解包访问。没有手写重复 DTO、直接业务 fetch 或引入额外状态库。

## 已实现

- 四个 Server 路由：/weaknesses、/weaknesses/[id]、/learning/explanation、/learning/explanation/[id]，复用登录门禁和个人导航偏好。
- 难点领域/标签/严重度/掌握/来源筛选、正式与候选和忽略/撤销历史、创建/编辑/确认/忽略/撤销/软删、追加证据/事件/复习版本。
- 精讲知识点或单难点、基础/深度/语言及明确资料范围、五部分文字卡片/自查要点/历史版本、引用来源、真实任务阶段/取消/重试、独立直接精讲历史与分页复习。
- 卡片再练只经 URL 传对象 ID/版本，由主 agent 接入现有练习计划确认流程。直接精讲和难点来源范围保持隔离。
- 输入草稿只在当前 owner 的 Query cache 中保留；sessionStorage 仅保存 owner 隔离的请求 UUID，用真实任务 lookup 恢复响应丢失，不保存回答、文件原文或卡片正文。
- 来源不可用或预览 GET 404/409 时取消/移除原文预览 cache；软删删除对应详情/卡片/预览 cache，不清除其他资产。
- 并发编辑错误保留当前字段；用户明确读取最新版本后才用新 expected_version。确认/状态/创建/删除后刷新真实 profile 活动项。
- 选择已有精讲的正式难点时复用绑定精讲的重新生成接口，保留本次基础、深度与语言输入；资料范围沿用该难点。旧 URL 的历史任务不覆盖当前真实任务；重新生成的请求 UUID 按 owner 与目标隔离保存，响应丢失后可通过 lookup 恢复。

## 实际验证

已通过 `pnpm typecheck`、`pnpm lint`（包括 API 边界）、本 feature Oxfmt。

`pnpm exec vitest run src/features/learning-assets`：6 文件、14 测试全部通过。验证真实 SDK 的 202/鉴权/no-store/字段 presence、409 HTTP/ApiError与不自动写重试、failed只读查询、五部分与自查不产生评分、默认字段省略、绑定难点 scope 固定、版本错误输入保留、父来源失效 cache 删除、预览 404 独立清原文 cache、软删只清关联资产 cache；新增页面回归覆盖正式难点复用绑定精讲、旧完成任务 URL 下当前新任务优先、响应丢失后刷新 lookup 恢复及请求元数据 owner/target 隔离且不保存正文。

API 测试使用真实生成 SDK 配合合成 transport；组件/Query 测试使用合成数据。这些不代替真实后端接口门禁、数据库迁移、worker/model 成功、浏览器闭环、四宽度截图、字体命中或人工语义/设计验收。

## 未在此 subagent 验证

浏览器真实用户路径、375/768/1024/1440 实际渲染与字体、真实模型及资料精讲、业务数据库迁移由主 agent 集成验证。本 subagent 未执行 build、DB 写入、commit、push 或 PR。

自审向后端报告了难点改名后精讲 config.topic 与 concept_key 冲突。后端已修复默认重新生成按当前目标快照，并补旧卡片版本保留回归；前端调整绑定配置时也读取当前本人难点名称，不改已有版本。该后端回归结果由后端/主 agent 报告。Pen 元数据与渲染 bounds 冲突见 README，未冒充无警告验收。
