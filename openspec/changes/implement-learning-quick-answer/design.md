# Design：学习快速回答

## 数据与执行
LearningConversation 复用 UUID、时间、软删除与 actor mixin，固定 owner、mode、knowledge_base_id、file_ids。LearningTurn 为追加式问答及运行记录，保存 request_key、问题摘要、状态、租约 token/期限、答案、结构化引用、trace_id、不可变 Prompt fingerprint、模型参数、耗时和稳定错误码。正文仅存业务表，日志不存正文。会话级 PostgreSQL 行锁用于短事务领取；耗时检索/生成事务外执行；完成时复核用户、会话、来源活动版本，并以 token 防止过期执行覆盖新结果。同会话最多一个处理中请求；重复 key 不重复调用模型，失败允许同 key 重试，换问题复用 key 返回冲突。

## 证据与历史
检索复用 RetrievalService，最多 8 片段。生成结构为 answer、refused、citation_ids；模型只引用本次证据序号。无证据服务端直接拒答；资料模式非拒答必须提供有效引用，未知/重复引用或空输出拒绝。返回前复核授权活动版本，来源发生变化则本轮失败，防止用户收到删除/移动/旧版片段。历史详情保留问答，但撤权后引用正文和文件名隐藏；后续问题只传前 6 条用户问题，不传旧回答/旧片段，指代问题把近期问题一并检索。不把用户资料或历史写入系统指令。

## 模型与 Prompt
用户指定 qwen3.8-flash，复用 AI_BASE_URL/DASHSCOPE_API_KEY。LangChain ChatOpenAI 进入真实调用，enable_thinking=false；严格 JSON Schema 输出后仍由 Pydantic 与业务引用门禁验证。公共规则、角色和场景规则为代码版本化不可变组合，记录各片段 hash 与输入/输出 Schema hash；升级需显式改版本。此次没有数据库 Prompt 发布指针与管理员编辑 API，不宣称完整提示词管理已实现。外部超时/连接错误、429/5xx、鉴权错误、截断或非法结构均稳定失败；不打印上游异常原文，不调用其他厂商。

## HTTP 与前端
使用统一 ApiResponse/PageResponse/RFC 9457，私有路由 no-store。OpenAPI 生成 DTO，feature API -> queryOptions/mutationOptions -> UI。首版请求等待完整结构化结果，展示检索与生成处理中及明确失败；不假装流式输出或准确百分比。请求总超时受服务端配置控制；失败保留输入，重试沿原 key。既有 AI 确认门禁复用并扩充说明为问题、近期问题及资料片段，不改旧确认含义；新版本确认需本人操作。页面复用现有组件与象牙白/阳光黄样式，不新增依赖。

## 检索评测
合成中文 corpus 与精确/同义/无答案问题，不含用户原件。从真实 Trace 的 keyword/vector/fusion/rerank 候选计算 Recall@5、MRR、nDCG 与无答案率；明确关键词基线是 PostgreSQL ts_rank_cd，不能误称实际 BM25。消融采用同一授权候选的独立排序，no-rerank 与 hybrid-only 如相同须注明；报告 P95/错误率及模型/策略版本，不用 deterministic provider 冒充真实模型质量。

## 评测驱动修订
2026-10-02 首次合成集关键词 Recall@5=0：plainto_tsquery 将自然问句所有词作 AND，问句功能词不在原文导致漏召回。改为安全分词后的 websearch OR 查询，继续通过 PostgreSQL 授权与 rank 排序，策略升到 v2；不调整分块、模型或向量维度。重排阈值不代表充分证据，补充用真实生成模型验证无答案拒答，不能调高阈值凑指标。

回答语言作为 AnswerRequest.language（zh/en，默认 zh）进入代码上下文和运行模型参数，页面显式选择；同 key 不允许换语言。中文模式的纯长英文输出稳定拒绝，合法技术词和数字不受影响。拒答也按所选语言显示，不让英文资料决定输出语言。
