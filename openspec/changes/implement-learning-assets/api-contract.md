# 接口契约草案：难点资产与文字知识精讲

状态：2026-10-03具体方案已批准，进入实现阶段；已冻结后端schemas/models，API可调用性须待真实验证。实施以FastAPI Pydantic/OpenAPI为唯一事实源，生成SDK，不手写前端DTO。

冻结输入：title最多120字、topic最多500字、标签最多20项/每项60字，选中文件最多100个且不得重复。基础枚举unfamiliar/know_concept/used_unfamiliar/review，深度quick/systematic/deep，语言zh-CN/en-US。卡片单段最多6000字、正文总预算40000字，示例与理解练习各最多10项，引用最多30项。资料检索top_n=8、合计证据预算32000字符，超预算明确失败而非静默截断；上游响应预算250000字符且必须完整结束。API错误/阶段由后端Schema生成，限制是执行预算，不用于推断用户能力。

## 通用规则

前缀 `/api/v1`；所有对象 owner隔离，非本人和管理员业务正文访问404；私有正文 no-store。复用统一成功/分页响应、RFC9457及ApiError，HTTP与code一致。写操作携带 expected_version；任务/创建携带 UUID request_key。GET 不识别、不生成、不改状态。

## 难点与证据

| 方法/路径 | 请求 | 结果 |
| --- | --- | --- |
| GET /weaknesses | page/page_size、query、tags、severity、mastery_state、decision | 200 本人分页；默认正式活动难点，候选通过 decision显式筛选 |
| POST /weaknesses | title、可选domain/tags/severity、source_mode及资料范围、request_key | 201 手动正式难点＋manual声明/确认快照＋首次卡片run引用，或相同key原结果；不伪造评分、不隐式取用户全部资料 |
| GET /weaknesses/{id} | — | 200 资产/候选、version、可用证据、状态/复习历史、活动卡片及run；失效正文隐藏 |
| PATCH /weaknesses/{id} | expected_version、title/domain/tags/severity | 200 更新；首版来源模式/知识库/选中文件范围不可变，改变范围需新建直接精讲或手动难点 |
| POST /weaknesses/{id}/confirm | expected_version、request_key | 200 正式资产及首次生成run；低置信度/单题候选可明确确认 |
| POST /weaknesses/{id}/ignore | expected_version | 200 忽略当前候选证据，原事件不反复重现 |
| POST /weaknesses/{id}/revoke | expected_version | 200 撤销正式识别，保留历史，终止未发布卡片 |
| PATCH /weaknesses/{id}/mastery | expected_version、mastery_state | 200 状态及追加事件；不得把用户标记当系统验证通过 |
| DELETE /weaknesses/{id} | expected_version | 204 软删除，不删旧练习/评分 |
| GET /weaknesses/{id}/reviews | page/page_size | 200 复习/验证版本、实际覆盖与来源可用性，不伪造掌握概率 |

候选/正式决定和掌握状态为两个字段；UI不可用一个“状态”把 pending 与 mastered混为同一状态机。列表返回 card/run摘要，不在列表响应复制完整回答/卡片。

## 精讲与卡片任务

| 方法/路径 | 请求 | 结果 |
| --- | --- | --- |
| POST /learning/explanations | topic或weakness_id/version、基础/深度/语言、source_mode/knowledge_base_id/file_ids、画像字段存在性、request_key | 202 私有 explanation＋KnowledgeRun；直接精讲不创建Weakness |
| GET /learning/explanations | page/page_size | 200 本人精讲历史摘要 |
| GET /learning/explanations/{id} | — | 200 配置、当前卡片、来源状态与run |
| GET /learning/explanations/{id}/cards/{version} | — | 200 指定不可变版本，旧来源不可用时隐藏原文预览 |
| POST /learning/explanations/{id}/regenerate | expected_version、明确新配置或原配置、request_key | 202 新run；绑定难点时保持相同逻辑来源范围，可显式采用当前处理版本；直接精讲可明确改变范围。成功才切换卡片版本，旧卡片不覆盖 |
| DELETE /learning/explanations/{id} | expected_version | 204 软删除，阻止未发布结果 |
| GET /learning/knowledge-runs/{id} | — | 200 真实状态、阶段、retryable、error_key、result_ref |
| GET /learning/knowledge-runs | request_key | 200 本人对应run；响应丢失恢复，不存在404 |
| POST /learning/knowledge-runs/{id}/cancel | — | 200 pending取消或processing登记取消；终态发布后409 |
| POST /learning/knowledge-runs/{id}/retry | 原input_digest与request_key | 202 仍合法的failed重新入队；已取消需新操作key |

KnowledgeCardView另含不可变config（该卡片版本的topic与完整来源配置），针对性练习必须据此预填，不得从正文概念或引用反推范围。报告Review字段仅在当前refs匹配持久版本时返回version，否则version=null并纯派生当前结论；GET不写入。

KnowledgeCardSchema：concept/applications、principles、examples、misconceptions、exercises/self_check_points、citations/source_mode；区分用户基础与生成内容，不返回系统Prompt。来源模式与引用由服务端固化；不能让模型选择陌生file/chunk或返回虚假的已执行代码结果。KnowledgeRun result_ref指向具体 explanation/card version，不从活动指针猜该run结果。

## 现有接口的最小接入

- PracticeConfig新增可选单个判别联合`learning_target`，为`weakness(id/version)`或`explanation(id/card_version)`；服务端校验owner并解析目标上下文与合法来源，显式字段优先。系统验证只计以目标概念为唯一topic的题，相关未答/未评分/低置信度不能筛掉；普通配置省略时行为兼容。
- 保留target但显式主题/模式/资料范围与目标不兼容时，在plan前返回422 LEARNING_TARGET_MISMATCH并保留输入；用户显式移除target可用普通练习。目标版本改变或来源失效依旧409，不静默覆盖输入或自动扩大来源。
- 练习plan/revision固化target引用；旧attempt不可变。提交、评分、完成、重评及来源练习删除各自通过同事务持久事件触发Review投影，报告响应只增加相关目标/候选及证据状态，不覆盖原分数/建议。直接精讲目标不产生隐式Weakness；可由本人精讲详情读取对应复习摘要。
- UserProfileView.active_weaknesses读取当前owner、confirmed、未撤销/删除且有效practice或manual证据、未mastered的活动项；manual说明为用户主动学习目标，不冒充系统诊断；空数组仍可合法出现，但必须由查询结果产生。
- 卡片/证据预览复用受保护的来源查询与统一feature API，不开放新的管理员查询正文接口。

## 稳定失败

| HTTP/error_key | 行为 |
| --- | --- |
| 404 LEARNING_ASSET_NOT_FOUND | 不存在/已删除/非owner，不泄露存在性 |
| 409 LEARNING_ASSET_VERSION_CONFLICT / LEARNING_ASSET_DUPLICATE | 保留输入，陈旧更新/精确键碰撞不静默覆盖 |
| 409 LEARNING_ASSET_KEY_CONFLICT / KNOWLEDGE_RUN_CONFLICT | 同key不同输入/已发布终态/非法并发 |
| 409 LEARNING_ASSET_SOURCE_CHANGED | 来源/目标版本改变，阻止生成/发布，旧结果保留 |
| 422 KNOWLEDGE_CONFIG_INVALID / KNOWLEDGE_EVIDENCE_INSUFFICIENT | 缺必要输入/资料不足，不自动改通用模式 |
| 422 LEARNING_TARGET_MISMATCH | 显式练习主题/来源与保留target不兼容，用户调整或明确移除关联 |
| 502 KNOWLEDGE_OUTPUT_INVALID | 模型结构/内容/引用门禁失败，保留旧卡片 |
| 422 KNOWLEDGE_CONTEXT_TOO_LARGE | 证据超出执行预算，拒绝而非截断 |
| 502 KNOWLEDGE_RETRIEVAL_INCOMPLETE | 检索Trace未完整，保留旧卡片 |
| 503 KNOWLEDGE_PROVIDER_UNAVAILABLE | 模型未配置或不可用，明确可重试状态 |
| 504 KNOWLEDGE_RUN_TIMEOUT | 任务/租约超时，旧token不能发布 |

GET run成功读取failed任务仍返回200及failed状态；这不是用200包装HTTP请求失败。实施复用已有错误类别及ApiStatusCode，并测试HTTP/code/OpenAPI一致性。
