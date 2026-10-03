# 接口契约草案：学习刷题练习

状态：供方案审查的 FastAPI 契约设计，尚未导出 OpenAPI，不能当作已可调用接口。实施时由后端 Pydantic/路由生成 OpenAPI 和前端 SDK，不手写重复 DTO。

## 通用约束

前缀 `/api/v1/learning/practice`；当前用户私有，所有对象查询校验 owner，其他用户及管理员通过猜 ID 访问业务正文返回 404。列表不返回别人资源。HTTP 状态与 envelope code 一致，私有正文 `Cache-Control: no-store`；错误复用 RFC 9457/项目 ApiError。

生成/重新生成/提交/重评使用 UUID request_key 和规范化 input_digest；编辑/开始/草稿保存/完成携带 expected_version。输入字段存在性决定画像兜底，明确 null/[] 不被 profile 补回。副作用不由 GET 触发模型。

## 操作

| 方法与相对路径 | 请求要点 | 结果与成功状态 |
| --- | --- | --- |
| POST /sets | 配置、source mode、知识库/文件、主题、画像覆盖、题型分布、难度、题量、request_key | 201 私有配置草稿 |
| GET /sets | page/page_size | 200 本人分页历史摘要 |
| GET /sets/{id} | — | 200 配置、当前题集及本人历史 attempt 摘要；来源可用性实时复核 |
| GET /sets/{id}/plans/{plan_version} | — | 200 该不可变方案的原配置/推荐候选、摘要与有效上下文；不含系统 Prompt |
| GET /sets/{id}/revisions/{revision_id} | — | 200 指定题集版本、已确认配置、实际题量、题目/规则与实时来源可用性 |
| POST /sets/{id}/plan | expected_version、request_key | 202 RunView；完成后读取 AI 原配置/推荐配置候选及摘要、有效上下文和 plan_version；尚不生成题目 |
| POST /sets/{id}/generate | expected_version、plan_version、candidate、confirmed_config_digest、request_key | 202 RunView；完成后 result_ref 指向新预览 revision，资料不足为 failed |
| PATCH /sets/{id} | expected_version、标题/非来源配置 | 200 新 version；配置变化使旧 plan 失效，旧 revision/attempt 不变；切换来源新建 set |
| DELETE /sets/{id} | expected_version | 204 软删除，后续读取不可用且运行不再发布 |
| PATCH /sets/{id}/questions/{question_id} | expected_version、完整题目/答案/规则 | 200 新不可变 revision；部分不一致修改不发布 |
| DELETE /sets/{id}/questions/{question_id} | expected_version | 200 新 revision 及实际题量；0 题题集不允许开始 |
| POST /sets/{id}/regenerate | expected_version、base_revision_id、可选 question_id、request_key | 202 RunView；复用该 revision 已确认上下文和实际题量/题型，单题保持题型/难度；当前配置改动后须重新 plan/confirm/generate |
| POST /sets/{id}/attempts | expected_version、revision_id、request_key | 201 active attempt，题集快照固定 |
| GET /attempts/{id} | — | 200 题目、当前题、本人草稿、提交/评分历史、version |
| PATCH /attempts/{id}/answers/{question_id} | expected_version、题型匹配答案、current_question_id | 200 已保存草稿及新 version |
| POST /attempts/{id}/questions/{question_id}/submit | expected_version、answer_version、request_key | 客观题 200 SubmissionGradeView；主观题 202 RunView 含已固化 submission_id，失败/取消保留 submission |
| POST /submissions/{id}/regrade | reason、request_key | 202 RunView，完成后 result_ref 指向追加的主观 grade 版本；客观评分无需重评模型 |
| GET /submissions/{id}/grades/{grade_version} | — | 200 指定不可变点评版本、规则和回答快照关联，不从最新指针猜测该 run 结果 |
| POST /attempts/{id}/complete | expected_version | 200 completed attempt 与完整/未提交覆盖信息，不隐式提交草稿 |
| GET /attempts/{id}/report | — | 200 本人逐题结果/错误原因、知识点结果、评分版本、未答/未评分覆盖信息与符合规则时的汇总 |
| GET /runs/{id} | — | 200 实际阶段、有效状态、重试信息和 result_ref，不含系统 Prompt/原始上游异常 |
| GET /runs | request_key、operation、目标对象 ID | 200 当前 owner 的对应 RunView；不存在返回 404，用于首个响应丢失后恢复 |
| POST /runs/{id}/cancel | — | 200 立即取消 pending 或登记 cancel_requested；发布/终态返回稳定冲突 |
| POST /runs/{id}/retry | 原 request_key、原 input_digest | 202 重新入队失败且仍合法的 run；复用原 submission，终态取消需新操作 key |
| PATCH /feedback | question_revision 或 grade 引用、helpful/unhelpful/null | 200 本人反馈状态，重复写幂等 |

## 服务端模型边界

- PracticeConfig：mode 固定 practice；source_mode 为 materials/general；资料模式须有效本人知识库，文件属于该库且有活动解析版本。通用模式不携带知识库范围；主题与可选岗位/技能/知识点形成可出题上下文。
- QuestionSnapshot：question_id/type/difficulty/topics/stem/options/answer/answer_explanation/rubric/source_refs；五型采用判别联合，本期限制与默认值见 design。资料引用只接受本次授权证据编号，后端转换为文件/处理版本/chunk/页码或段落。
- AnswerValue：单选 option_id，多选 option_ids，判断 bool，简答/文本编程 text；不能把任意 JSON 当合法答案。
- GradeView：submission_id/version、逐维度等级、可选 score/max_score、回答证据位置、confidence（模型自报）、low_confidence、missing_points/error_reasons、suggestions、topics、知识来源类型；不返回系统 Prompt 和私有 trace 正文。
- RunView：id/operation/status/stage/attempt_count/retryable/error_key/submission_id/result_ref；result_ref 为 type/id/version 判别结构，plan/revision/grade 分别对应上表的指定版本 GET。异步终态失败在 GET RunView 中展示实际失败状态而非错误 envelope；提交/权限/版本等 HTTP 请求自身失败仍用错误响应。

## 失败行为

| HTTP | error_key 示例 | 含义 |
| --- | --- | --- |
| 422 | PRACTICE_CONFIG_INVALID / PRACTICE_EVIDENCE_INSUFFICIENT | 用户配置缺失/题型答案不合法，或选定资料不足以出题 |
| 409 | PRACTICE_VERSION_CONFLICT / PRACTICE_PLAN_STALE / PRACTICE_RUN_PROCESSING | 陈旧版本/建议、pending/processing/cancel_requested 重复或有这些状态的初次评分时完成练习 |
| 409 | PRACTICE_KEY_CONFLICT / PRACTICE_SOURCE_CHANGED / PRACTICE_ATTEMPT_COMPLETED | 同 key 不同输入、来源改变、已完成 attempt 的答案写入 |
| 404 | PRACTICE_NOT_FOUND | 对象不存在、已删除或当前用户无权访问 |
| 502 | PRACTICE_GENERATION_INVALID / PRACTICE_GRADE_INVALID | 模型结构/题目质量/评分证据未通过校验 |
| 503 | PRACTICE_PROVIDER_UNAVAILABLE | 供应商不可用或受限；前端明确重试，不重复提交 |
| 504 | PRACTICE_RUN_TIMEOUT | 有界模型/请求/租约超时，不允许迟到结果发布 |

实施复用现有 AppError 子类和 ApiStatusCode，error_key 可关联 run ID；不另建响应协议、不用 HTTP 200 包装失败。前端保留输入并显示可执行的调整或重试操作；不自动换成通用出题，不伪造进度百分比。本文的错误 extension 需在现有 RFC 9457 扩展机制内增加最小公开运行引用，不暴露正文。
