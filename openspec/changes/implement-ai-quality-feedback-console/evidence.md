# Evidence：AI 质量反馈与管理员诊断台

## 已确认事实

- 用户在 2026-08-30 明确要求：为普通用户增加类似电商投诉的“我要反馈”，收集必要信息；管理员登录后能够查看工单并根据 RAG 链路排查问题。
- 既有 PRD 明确管理员不能自由查看用户资料、回答和任务正文，因此本变更采用“用户主动提交 + 单次请求基础授权 + 追加字段另行授权”的最小披露模型，而不是扩大管理员全局权限。
- `implement-document-parsing-indexing` 已在规格层补入 `RetrievalTrace`、不可变策略版本和消融评测要求；业务代码尚未实现，因此本变更当前只有需求和设计证据。

## 外部材料的使用边界

- 用户提供的微信文章《RAG 跑通之后，我才发现真正缺的是一个“运维平台”》提出 request/trace 定位、策略版本、离线评测、Shadow/Canary、回滚和成本归因等治理方向。
- 本变更只吸收与当前问题直接相关的 Trace、反馈绑定、隔离回放、消融诊断和管理员处理闭环。
- 文章属于产品营销材料；其行业比较、固定阈值、字段数量、自研引擎必要性和成本精度未作为事实或验收门禁。

## 当前验证边界

- 已创建 Proposal、Design、Tasks 和两份增量 Specification；尚未实现迁移、API、前端页面、加密快照、权限矩阵或回放 runner。
- 当前没有 OpenSpec CLI 可执行证据；结构检查和 `git diff --check` 不能冒充 strict validate。
- 本轮未运行 Next.js build、Docker build、后端测试、前端测试、真实 curl 或浏览器验收，因为没有业务代码实现。


## 2026-10-03 本地实施核验补充

本机 `main@57629ef` 已有真实问答、练习与学习资产执行器和检索 Trace，原文“尚无真实业务 Agent”等表述属于历史记录，不代表当前基线。当前仍没有本变更的领域模型/API/页面。具体首批范围、公共契约、迁移顺序、文件归属与验收条件见本目录 `implementation-plan-20261003.md` 及 `docs/development/parallel-next-batch-20261003.md`；方案待用户批准，尚未开始本变更实现。

已修正文档的 OpenSpec delta 头及 Requirement/Scenario 标点解析格式，未改产品规则；当前 CLI strict validate 通过。旧规格的 BM25/完整回放能力仍须按本地实际 FTS 与离线对照边界校准，并在实施批准前同步设计/spec；不将解析通过当成功能交付。


## 2026-10-03 已批准首期质量后端实现与专项验证

历史段落中的“尚未实现/待批准”只描述当时状态。用户随后批准本期范围、独立 worktree 并行开发及必要本地提交。后端分支为 `codex/learn-quality-backend`，worktree 为 `/Users/lilin/Documents/Codex/2026-10-03/task/worktrees/next-quality-backend`；真实接口基础提交为 `cc7fd93`，授权、清理与集成回归提交为 `b6cedcb`。

### 实现范围与真实能力

- 六张质量领域表：`ai_quality_cases`、`ai_quality_case_events`、`diagnostic_access_grants`、`diagnostic_snapshots`、`diagnostic_replays`、`diagnostic_audits`。公共迁移/注册由集成负责人提交 `459ea2c`；负责人报告隔离库升级至 07、降至 04、再升级 07 和 Alembic schema check 通过。本专项不迁移业务库、不读取真实正文或调用真实模型。
- 实现本人创建幂等、本人列表/详情/消息、追加授权批准/拒绝/撤销、未领取撤回、独立用户关闭/确认，以及管理员脱敏概览/队列/详情/领取转交/状态转换/公开回复/内部备注/逐字段快照/候选离线对照。真实 Pydantic 契约已冻结：15 paths、17 operations、32 schemas。
- 首期只适配本人资料模式、已成功且完整 Trace 的 LearningTurn；所有管理员正文通道重新检查 owner 活跃状态、结果来源、KB、资料绑定、文件、chunk 与当前 processing version。短事务按 Case→Grant 锁序序列化读取和撤销，来源表共享锁防版本撤销竞态。来源失效时事件正文也停止解密。
- Fernet keyring 支持旧 key 读取、新 key 写入，密文绑定工单/授权 scope，无未配置密钥降级。审计只含固定事件/字段/原因码/标识与版本，不存正文。成功及失败真实 HTTP 均 no-store；角色判断先于 ID 查询。
- 五种回放为已记录候选的 `fts_only`、`vector_only`、`hybrid_only`、`without_rerank`、`full` 排序对照，无新增召回、模型调用或生产配置变更。FTS 不标记成 BM25；记录阶段耗时不是独立模式延时，`independent_latency_ms=null`、`causal_claim=false`。缺少真实阶段/策略或当前来源失效明确返回 RFC 错误，并持久化无正文 failed 回放记录。技术处置结论要求对应模式与 full 的证据差异，不能用来源失效/Trace 缺失证明算法归因。
- 提交频率限制来源于 feedback/spec 的“提交频率超限”场景，首期配置为 `Settings.ai_quality_case_hourly_limit=20`；同请求重试/活动工单幂等不消耗新建额度。现有验收实现界限为描述 4000、期望 2000、消息 4000、授权理由 1000、处置摘要 2000 字符，候选追加授权最多 64 个 ID；显式基本授权没有默认勾选值。
- `maintain_quality(session, settings, now=None)` 位于 `backend/src/xuemian_ai/ai_quality/maintenance.py`，使用调用方已有事务，无内部 begin/commit。立即拒绝到期、撤销或有效关闭后的读取；失效 7 天清正文/快照；自动确认关闭、180 天元数据和匿名审计保留、软删除 owner 即时撤销清正文与匿名化；共用 Trace 的保留按所有工单最大有效期限计算，仍受 occurred_at+180 天上限约束。

### 已执行验证

- 使用独立锁版本 Python 环境与专属隔离 PostgreSQL harness，合成用户、资料、结果和 Trace；数据库目标通过 `environment=test` 和 `current_database()` 双重检查。专项 pytest **82 passed**：18 个真实 PostgreSQL/HTTP 集成场景 + 64 个 policy/diagnostics/maintenance/result_sources 单元测试。
- 覆盖并发创建幂等、请求键冲突、跨用户/跨工单、字段范围、追加授权批准拒绝与撤销、五类来源失效、内部备注隔离、五模式对照、失败回放记录、确认/到期即时拒读、7/180 天清理、owner 删除和审计匿名化。两项并发测试证明读取期间撤销/当前版本退休被锁阻塞，读取提交后下一次访问立即拒绝。
- 修复真实服务撤销授权的 SQLAlchemy onupdate 异步属性读取故障；补充真实 HTTP DELETE grant 回归，返回 200 且 no-store。HTTP 角色优先、错误状态、验证输入和脱敏队列亦有回归。
- Ruff check / Ruff format check 通过；mypy 9 个质量模块/路由源文件通过；`git diff --check` 通过。OpenSpec `validate implement-ai-quality-feedback-console --strict` 通过。最终提交后复核仍为 82 passed（4.64 秒）。

### 剩余统一验收与限制

- Scheduler 接线、真实完整服务 curl 权限矩阵、OpenAPI/SDK 重新生成、前端验证和用户人工验收由集成负责人执行；本专项不以单元/ASGI HTTP 测试代替上述验收，也未运行 Next.js/Docker 构建。
- 维护首期扫描并锁定待处理工单/Trace，尚未进行大规模数据性能测试；后续可在真实规模证据支持下批次化，不把当前实现宣称为吞吐量结论。
- 离线候选对照只证明已记录排序差异；不支持重跑 parsing/indexing，不提供因果归因或独立模式延时结论，未能得到批准证据的技术结论返回 `QUALITY_ATTRIBUTION_UNVERIFIED`。

## 2026-10-03 首期统一集成与实际浏览器

本期后端、SDK、两端 UI、共享角色 guard/导航、真实运行快照与调度清理已在独立分支完整集成。最终后端 506 passed / 41 skipped，前端 49 files / 252 tests，Ruff/format/mypy、真实 32 项 curl、OpenAPI 字节一致、迁移上下回合及 schema check、Next/Python 构建与两份 OpenSpec strict validate 通过。真实单一 Ego 浏览器完成两学习账号/管理员权限、授权/正文隔离、公开内部备注、撤销/关闭、Prompt 草稿/Diff/无模型预览/发布门禁/回滚新版本/启停/原生历史恢复；375px 页面无横向溢出。

全部使用合成库与资料，未运行外部真实模型；原 Pen 缺失已获用户“授权设计”改用仓库截图，不宣称原稿或用户人工验收通过。20 张实际证据已保存，最终补充截图接口超时以 DOM 状态完成最后检查。临时数据库和本轮进程已清理，worktree 保留；未推送、PR、部署或迁移业务库。完整具体矩阵、发现并修复的问题、分支提交及真实限制见 [统一交付记录](../../../docs/development/quality-prompt-delivery-20261003.md)。
