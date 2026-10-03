# Design：AI 质量反馈与管理员诊断台

## 1. 产品边界

该能力是“用户主动发起的质量投诉工单”，不是管理员全局数据浏览器。诊断闭环为：

```text
AI 结果 + trace_id
  → 用户点击“我要反馈”
  → 选择问题类型、描述问题、确认单次请求授权
  → 创建质量工单和固定授权快照
  → 管理员领取并查看链路
  → 必要时请求追加授权
  → 隔离回放/消融定位
  → 管理员公开回复和归因
  → 用户确认或系统关闭
  → 进入脱敏质量统计与评测集候选池
```

## 2. 领域模型

### 2.1 `AIQualityCase`

- `id`、稳定 `case_number`、`user_id`
- `source_type`、`source_id`、`trace_id`
- `category`：`not_found | irrelevant_source | wrong_answer | wrong_citation | outdated_content | slow | other`
- `description`、可选 `expected_result`
- `status`：`submitted | triaging | waiting_user | investigating | resolved | closed`
- `assignee_id`、`resolution_code`、`resolution_summary`
- `created_at`、`updated_at`、`resolved_at`、`closed_at`

同一用户对同一 `source_type + source_id + trace_id` 的活动工单使用幂等约束，避免重复点击创建多个工单。描述和期望结果是敏感用户输入，不进入普通日志。

### 2.2 `AIQualityCaseEvent`

追加式时间线，包含状态变化、用户补充、管理员公开回复、管理员内部备注、授权请求、授权变化和回放完成。事件使用 `visibility=user | admin` 区分；后端响应模型按角色构造，不能依赖前端隐藏内部备注。

### 2.3 `DiagnosticAccessGrant`

- 工单、授权用户、申请管理员和用途；
- 允许字段枚举，不接受任意 JSONPath：`query`、`final_output`、`final_citations`、`candidate_excerpts`；
- 允许的 `trace_id`、chunk ID 集合和可选 source ID；
- 生效、到期、撤销时间；
- 授权版本、用户确认时间和展示文案摘要；
- 状态：`pending | active | expired | revoked | rejected`。

创建工单时的基础授权固定为单次请求的 `query + final_output + final_citations + trace_metadata`，有效期为 30 天或工单关闭时间两者中较早者。`candidate_excerpts` 必须由管理员说明原因并由用户追加授权，追加授权最长 30 天且不能超过工单有效期；整份文件、对象存储地址、向量和同会话其他消息不属于可授权字段。

### 2.4 `DiagnosticSnapshot`

用户确认基础授权时，在短事务内固化该请求当时的 Query、最终输出和最终引用，不随后续内容编辑而漂移。快照使用应用层加密或数据库受控加密，密钥不进入数据库和日志；读取必须同时满足工单、角色、有效 grant 和字段范围。

### 2.5 `DiagnosticReplay`

记录回放请求、策略快照、消融模式、状态、指标、差异摘要、错误码和执行人。回放不保存新的正文副本，不写用户会话，不修改活动索引或策略指针。

## 3. 状态机

- 创建后为 `submitted`；管理员领取进入 `triaging`。
- 需要用户说明或追加授权时进入 `waiting_user`；用户补充后回到 `triaging`。
- 开始回放或工程定位进入 `investigating`。
- 管理员必须填写 `resolution_code` 和用户可见结论后进入 `resolved`。
- 用户确认、用户主动关闭或解决后超过可配置确认期进入 `closed`。
- 用户只能在 `submitted` 且尚未被领取时撤回工单；其他阶段可以撤销正文授权，但工单状态和脱敏审计继续保留。
- 状态转换由后端白名单校验，并使用乐观锁或版本号阻止并发覆盖。

## 4. 权限与隐私

### 4.1 普通用户

- 只能从自己的真实 AI 结果创建工单，只能查看和补充自己的工单。
- 不能提交任意 `trace_id` 绑定他人请求；后端按当前用户、source 和 trace 三者重新校验。
- 授权框不得默认勾选；提交前展示字段、用途、查看角色和默认有效期。
- 可以拒绝或撤销追加授权。撤销后新的正文读取立即失败，已发生访问只保留不含正文的审计事实。

### 4.2 管理员

- 工单列表默认只返回工单号、用户 ID/脱敏账号、类型、状态、版本、负责人和时间，不返回正文。
- 打开详情先返回 Trace 元数据和授权状态；正文端点逐字段检查 grant，并记录成功或拒绝审计。
- 不提供按 Query/回答/片段正文全文搜索，不提供正文导出、原文件下载或跳转用户知识库。
- 管理员不能查看其他管理员的私密凭据，不能通过内部备注保存用户正文副本。

## 5. 管理员信息架构

### 5.1 质量概览

- 待处理、处理中、待用户补充、已解决数量；
- 按问题类型、业务类型、策略版本和日期的趋势；
- 首次响应时长、解决时长和积压时间 P50/P95；
- 高频错误码和重复问题聚类只使用脱敏标签，不自动展示正文。

### 5.2 工单列表

- 列：工单号、问题类型、业务类型、状态、策略版本、负责人、提交时间、最近更新时间；
- 筛选：状态、类型、时间、业务类型、策略版本、负责人；
- 排序：最久未处理、最近更新、提交时间；
- 不提供正文全文搜索和批量正文导出。

### 5.3 工单详情

- 顶部：工单状态、负责人、问题类型、提交时间和授权状态；
- 用户陈述：问题描述、期望结果、用户补充和公开回复；
- Trace 瀑布：解析/索引、Query、FTS、Vector、融合、Rerank、证据门禁、生成/引用的状态、候选数和耗时；
- 排名对比：同一 chunk 在关键词、向量、融合、Rerank 和最终结果中的排名、分数与过滤原因；
- 版本信息：解析器、分块、Embedding、融合、Rerank、提示词和模型版本；
- 回放对比：Baseline、FTS-only、Vector-only、Hybrid-only、无 Rerank 和当前完整策略；
- 时间线：领取、状态、授权、访问、回放、回复和解决事件。

诊断页只生成修复建议或评测集候选，不直接出现“发布策略”按钮。

## 6. API 边界

### 6.1 用户 API

| 方法与路径 | 行为 |
| --- | --- |
| `POST /api/v1/ai-quality-cases` | 校验 source/trace 所有权、创建工单和基础授权快照 |
| `GET /api/v1/ai-quality-cases` | 分页查看自己的工单 |
| `GET /api/v1/ai-quality-cases/{case}` | 查看自己的详情和用户可见时间线 |
| `POST /api/v1/ai-quality-cases/{case}/messages` | 补充说明 |
| `POST /api/v1/ai-quality-cases/{case}/grants/{grant}/decision` | 同意或拒绝追加授权 |
| `DELETE /api/v1/ai-quality-cases/{case}/grants/{grant}` | 撤销有效授权 |
| `DELETE /api/v1/ai-quality-cases/{case}` | 仅在未领取时撤回工单 |

### 6.2 管理员 API

| 方法与路径 | 行为 |
| --- | --- |
| `GET /api/v1/admin/ai-quality/overview` | 返回脱敏聚合指标 |
| `GET /api/v1/admin/ai-quality/cases` | 返回脱敏工单队列 |
| `GET /api/v1/admin/ai-quality/cases/{case}` | 返回工单、Trace 元数据和授权状态 |
| `GET /api/v1/admin/ai-quality/cases/{case}/snapshot` | 按有效 grant 逐字段读取授权快照并审计 |
| `POST /api/v1/admin/ai-quality/cases/{case}/assign` | 领取或转交 |
| `POST /api/v1/admin/ai-quality/cases/{case}/access-requests` | 请求追加候选片段授权 |
| `POST /api/v1/admin/ai-quality/cases/{case}/replays` | 创建隔离诊断回放 |
| `POST /api/v1/admin/ai-quality/cases/{case}/messages` | 创建公开回复或内部备注 |
| `POST /api/v1/admin/ai-quality/cases/{case}/transitions` | 执行受控状态转换和解决归因 |

所有接口继续使用现有响应、错误与 OpenAPI 规范。前端遵循组件 → query/mutation options → feature `api.ts` → 共享协议层 → generated SDK。

## 7. 回放和问题归因

本期仅对真实 Trace 已记录的候选排名进行离线对照，不重新执行线上检索或模型，不宣称独立负载耗时或因果消融。仅支持现有 `fts-jieba-or/vector/llama-rrf/qwen-rerank-v2` 策略；Hybrid-only 与无 Rerank 在当前实现中相同。来源或策略不可用时明确拒绝回放。

- 回放必须固定 Trace 当时的知识范围和可用策略版本；源资料已经删除或授权不足时明确返回不可回放，不从备份恢复正文。
- 回放模式至少包含 `fts_only | vector_only | hybrid_only | without_rerank | full`。
- 归因码至少包含：`parsing_gap | stale_index | fts_filter | vector_recall | fusion | rerank | evidence_gate | generation | citation | source_outdated | latency | not_reproduced | user_expectation | unknown`。
- “来源于某路”不是因果归因；只有消融对照或确定性错误证据才能选择对应技术归因。
- 工单解决后可以创建脱敏评测集候选，只保存人工重新编写或合法授权的 Query、目标 chunk ID 和标签；未经独立审核不得自动进入发布门禁集。

## 8. 保留与删除

- 普通 RetrievalTrace 默认 30 天；绑定工单后保留必要元数据至工单关闭后 90 天，总时长不超过 180 天。
- 授权正文快照在工单关闭、授权撤销或到期后的 7 天清理宽限期内物理删除；撤销立即阻止访问，宽限期只用于幂等清理。
- 不含正文的工单状态、解决归因和安全审计保留 180 天；聚合质量指标可以长期保留。
- 用户删除账号时立即撤销全部授权并清理正文快照；只保留依法和安全审计必要的匿名事件，不保留可反向关联的业务内容。

## 9. 验证策略

1. 状态机、幂等约束、授权字段白名单、到期/撤销和乐观锁单元测试。
2. 隔离 PostgreSQL 集成测试覆盖跨用户、普通用户/管理员角色、跨工单、撤销竞态、快照加密和清理。
3. 使用合成 Trace 验证各阶段瀑布、排名差异和五种回放模式，不使用真实用户正文。
4. 后端接口完成后先运行真实 curl 权限矩阵，再更新 OpenAPI 和前端 generated SDK。
5. 前端验证用户反馈表单、授权文案、工单列表，以及管理员概览、列表、详情、回放和内部/公开信息隔离。
6. 自审正文日志、错误响应、Prometheus label、浏览器缓存、搜索参数、导出/下载入口和管理员越权。
