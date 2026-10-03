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
