# Design：学习刷题练习第一版

状态：待用户确认；此文件是实现设计，尚无新迁移、API 或前端代码。

## 1. 产品流程

学习室“刷题评测” → 配置来源/知识点/题型/难度/题量 → AI 配置建议与摘要 → 用户确认生成 → 题目预览及编辑 → 开始练习 → 逐题保存/提交 → 点评及再次作答 → 汇总/私有历史。

二次确认沿用 PRD 的出题配置确认，不增加额外确认弹窗。AI 建议不得静默覆盖用户显式配置。PracticePlan 存原配置与完整推荐配置两个候选及各自摘要、有效上下文、基准 set version；用户可选择原配置或采纳推荐配置，generate 只提交 candidate 选择及已展示摘要，不自由覆写旧 plan。自定义修改经 PATCH 后使旧 plan 失效，重新取得方案再确认。预览可以查看答案与评分规则，练习允许提交后查看讲解和再次作答；不声称具备正式考试防泄题能力。

题量默认 5、范围 1–20；难度 easy/medium/hard，默认 medium；来源 materials/general；业务模式仅 practice。题型 single_choice/multiple_choice/true_false/short_answer/code_text。各题型数量之和等于题量。岗位、工作月数、岗位等级、技能、关注知识点和语言按字段读取现有画像；省略允许兜底，null/空数组禁用该字段兜底。无资料且无知识点/技能等可出题主题时在表单指出缺失项，不让模型猜测岗位或主题。effective_context 固化来源及画像版本，不自动更新资料。

## 2. 模块与数据

新增实际使用的后端 `practice/`、`api/practice.py` 和前端 `features/practice/`。复用既有持久化 Mixin、当前用户鉴权、统一响应/错误、Markdown 与引用预览能力；不引入第二套客户端协议。

| 对象 | 用途与关键字段 |
| --- | --- |
| PracticeSet | owner、标题、来源模式/固定知识库/文件范围、配置、effective_context、version、current_revision_id、软删除 |
| PracticePlan | owner/set、递增 plan_version、配置摘要/建议/effective_context、input_digest、基准 set version、run 引用；只存用户可见建议，不含系统 Prompt |
| PracticeRevision | 不可变题集版本、parent_revision_id、题目顺序及完整 question_snapshot、已确认配置/effective_context/plan 引用、实际题量/题型分布、source_mode/知识库/文件与证据版本快照、生成/编辑原因、模型与 Prompt 运行引用 |
| PracticeAttempt | owner、set/revision 引用、active/completed、当前题、version、开始/结束时间；旧 attempt 不随题集修改变化 |
| PracticeAnswer | attempt/question、version、当前草稿；明确保存成功后才能宣称已保存 |
| PracticeSubmission | 追加式提交、不可变答案快照、request_key；同一答案重放不重复追加 |
| PracticeGrade | submission、递增评分版本、规则快照、等级/可选分数、回答证据、置信度、建议、运行引用 |
| PracticeRun | owner、对象/操作类型、request_key/input_digest、pending/processing/cancel_requested/succeeded/failed/cancelled、lease token/期限、attempt、阶段、受保护输入引用/快照、result_ref、trace_ids、Prompt/Schema 指纹、模型参数、稳定错误码 |
| PracticeFeedback | owner、question_revision 或 grade 引用、helpful/unhelpful；唯一关联、可取消，无正文工单 |

题目 snapshot 包含稳定 question_id、题型、知识点、难度、题干、带稳定 ID 的选项、标准答案/要点、评分维度及规则、来源引用。每次编辑、删除或重新生成发布新 revision；事务先校验再切换 current_revision_id。旧 attempt 固定旧 revision；变更不覆盖历史，练习中也可返回预览编辑并为下一次练习创建新版本。删到 0 题允许保存预览但不能开始，页面要求补充题目；不强制恢复原配置题量。模型整组生成必须满足该次已确认题量，失败不能发布部分题集。

generate 发布 revision 时原子固化所选候选的配置/effective_context/plan 引用，并把 set 当前配置更新为该已确认候选。regenerate 明确携带当前 base_revision_id，沿用该版本已确认上下文，整组按其实际题量/题型分布生成（删除后的数量不得悄然恢复），单题只替换目标 question_id 并保持其题型/难度，不影响其他题。用户 PATCH 更改出题配置后必须重新 plan/confirm/generate，不能通过 regenerate 绕过确认。零题 preview 无可重新生成的题目，回配置流程重新确认生成。

异步结果引用使用 type/id/version 的判别结构，映射为本人 plan、revision 或 grade 的不可变读取端点。运行完成后读取指定版本，不依赖 set 当前指针；旧结果仍受当前所有权、删除与来源预览授权校验。

来源模式、知识库与文件范围在 set 创建后固定；PATCH 仅修改标题、主题、能力、题型/难度/题量及本次画像覆盖。切换知识来源或文件范围创建新题集上下文，旧 revision/attempt 的授权检查使用各自来源快照，不能读新配置覆盖旧来源。

本期报告为私有、基于已提交题目的聚合读取视图。报告返回提交覆盖数、逐题结果、最新评分版本与历史版本，并按知识点汇总本次正确/部分正确/错误/未评分题数及有证据的掌握情况、错误原因与建议；样本不足明确标记，不推断长期掌握度或创建 Weakness。没有覆盖全部题目及完整可加总评分规则时不生成总分。完成练习可以包含未答题或评分失败题，必须分别列出未提交/未评分，不把失败计为零分或正确。pending/processing/cancel_requested 的初次评分存在时不能 complete；completed 后可主观重评，报告更新时展示实际评分版本与处理中/失败状态，不覆写旧报告依据。

## 3. 执行与恢复

用 LangChain 调用现有 `qwen3.8-flash`，非思考模式；模型返回结构化结果后再经 Pydantic 和领域校验。不自行更换厂商。供应商若不支持 JSON Schema，沿用已有 JSON object + 本地严格校验方式，非法结构不通过。

LangGraph 在真实执行中组织“解析上下文 → 资料检索（仅 materials）→ 配置建议/题目生成 → 校验 → 发布”与“保存提交 → 客观判分或主观点评 → 校验 → 保存评分”。不同操作使用实际需要的节点，不建立未用角色。PostgreSQL 是运行、租约、题集及版本的事实源；无需另引框架检查点表替代领域授权。LangGraph 编排不代表节点可任意断点续跑：读取 PracticeRun 恢复界面，过期执行失败后用户明确重试整次操作，不能把上次未发布半成品写回。

模型操作使用持久化异步任务：API 短事务校验并保存 pending run/输入引用，立即返回 202 RunView，提交接口目标 P95 ≤ 2 秒；模型等待不占 HTTP 提交。新增轻量 practice-worker 轮询领取练习运行，事务外检索/模型调用，按租约心跳续期，完成短事务复核 owner、对象未删除、配置/来源版本和 lease token，再原子发布。复用现有模型超时配置，普通出题目标 60 秒内完成，超出目标继续显示阶段，达到明确任务超时上限才失败；本期任务超时建议 180 秒，待确认。

worker 并发由项目 Settings 提供可配置上限，不新增管理页面或处理外部服务生命周期。pending 任务在项目 worker 重启后可继续领取；processing 租约过期由 worker 标为失败，需用户明确重试，不能把未发布半成品当结果。前端通过 run ID 轮询真实状态，断线不取消任务，持有旧 token 的迟到返回不能发布。pending 可立即取消；processing 转 cancel_requested，在安全节点丢弃未发布结果后 cancelled，发布切换开始后不能接受取消；已有题目/答案/评分保留。失败重试增加 run attempt，不重复创建 submission；确定性非法结果不可自动重试，用户调整或明确重试。

客观判分可在短事务完成并返回 200；主观 submit 在同一入队事务固化 submission 并返回 202，失败和取消也保留该提交。状态查询只读，不调用模型或假装完成；后台恢复逻辑由 practice-worker 实际执行，不依赖 FastAPI BackgroundTasks 或内存任务生存期。

同 key 同输入：成功复用；pending/processing/cancel_requested 返回冲突和当前 run 引用，不重新入队；failed 可明确重试；cancelled 返回取消终态，不以同 key 重启。同 key 不同输入：409。重放先检查 owner/对象未删除与 key/input_digest，再判断新执行的 expected_version；不能因为第一次执行递增了版本而拒绝合法重放。更换配置或明确“重新生成/再次作答/重新评分”使用新 key 和新业务版本。编辑、开始、答案保存使用 expected_version，冲突不静默覆盖。答题保存排队，不让迟到的旧响应覆盖新草稿；未确认保存前保留本地输入并显示保存状态。

Run 在请求开始的短事务中创建；若请求断开前未拿到 run ID，客户端通过当前 owner 的 request_key 查找运行，未到达服务器则不存在，不自动重发模型调用。摘要绑定 operation、目标对象、原始业务输入和首次提交的 answer_version；expected_version 作为首次写前置条件保存，不随重试改写。首次提交用锁定的 answer_version 固化 submission，后续同 key 重试复用它而不读取新草稿。已取消 run 不以同 key 重启，明确重新发起用新 key；GET 显示无副作用。配置建议绑定基准配置摘要，修改配置使旧 plan 失效。开始 attempt 固定明确 revision；提交、保存和 complete 只允许 active attempt，completed 历史允许读取与主观重评，再次练习新建 attempt。completed 的失败评分仅可用该 submission 的 regrade 恢复，不恢复 completed 的答案写入。

## 4. 证据与题目质量

materials 每次出题只查询当前用户、指定知识库和文件的活动版本，复用 RetrievalService 与 EvidenceChunk。本期只基于有限检索片段出题，不承诺穷尽全文件知识点。run 记录 trace_id、策略版本和片段/处理版本引用。

输出可以为 evidence_insufficient，不生成题目。无片段后端直接终止；有片段不表示足够，模型须判断能否支持题干、答案及评分要点，用户可看到“资料不足”原因而不是伪造题目。资料题每题须绑定本次允许的 source IDs；未知/重复引用、来源不在范围或返回前活动版本变化都阻止发布。编辑也只接受该题集授权片段，不能输入任意用户文件引用。提交前和发布主观评分前重新核验来源；来源失效时仍可读历史业务结果，但不能继续用失效原文评分或生成，需选择当前有效资料产生新题集。general 及衍生报告保留“模型通用知识”标记。

题目质量校验：五类 Schema、题干非空、选项 ID 唯一、客观答案有效、单选唯一答案、多选非空合法集合、判断布尔答案、主观答案要点及评分规则、题目数量和题型分布、规范化题干/选项去重、来源。重复/不合法输出整次失败，不自动降级题型、数量或混入通用知识。语义支持与近义重复另由合成评测人工抽样，不宣称机械 ID 校验等同于语义保证。

## 5. 作答与评分

客观题按保存的规则执行：单选选项等值，多选集合完全匹配（顺序无关、不设隐式部分分），判断布尔等值。讲解采用生成/编辑时已校验的答案解释，返回实际错误原因（错选、漏选、多选等）、关联知识点和改进建议，避免只给对错或再调用模型改答案。多选若以后支持部分分必须另改规则与版本。该规则已经用户确认。

主观题根据题目规则和提交原文输出维度等级、对应证据、缺失要点、建议、置信度及可选分数；引用回答必须能匹配提交原文，引用未知评分维度、越界分数、缺失证据或编造运行结果均拒绝保存。无回答证据的缺失项标记 absent，不伪造引文。置信度是模型自报，不是校准概率；confidence < 0.7 标为低置信度（已确认的默认值），提供明确重评入口。代码只作文本点评，禁止展示“已编译/测试通过”。

每次再次作答产生新 submission。主观重评创建新 grade 版本并记录原因/模型/Prompt/输入引用，不覆盖旧评分；同 key 重放复用旧结果。失败保留已保存提交和旧评分，恢复后可重试。汇总清楚关联最新 submission 和其实际 grade，最新评分失败不拿旧答案评分冒充新点评；同 submission 重评失败时旧 grade 可读但最新重评失败必须明确展示。反馈仅保存本人选择，不自动改变评分或策略。

## 6. 前端与 Pen

沿用账号的左侧/顶部导航偏好，快速回答默认保持原样；仅本期刷题入口启用，知识精讲仍不可用。模式切换保存已确认的业务草稿，输入与结果按各自流程隔离。建议路由 `/learning/practice`、`/learning/practice/[id]`，由学习室三模式入口进入；私有练习历史位于本模式上下文侧栏。

2026-10-03 实际读取当前 Pen 文件 `/Users/lilin/.pencil/documents/374c64ee-02ba-4095-83eb-801344235851/pencil-new.pen` 图层、截图和布局问题：

| 原稿 | 节点 | 本期用途与须校准项 |
| --- | --- | --- |
| 10·刷题评测·创建 | SsFne | 保留配置与摘要布局；来源/画像使用真实数据；去掉本期简历/Weakness、限时、模板、乱序高级选项 |
| 11·AI确认与预览 | j59dgm | 确认配置先于生成题目；保留单题操作，增加真实答案/规则编辑与校验状态；文案切换为练习 |
| 12·正式答题 | Y3FY4 | 改为练习/逐题反馈，不显示倒计时；保存状态来自服务端；原三模式节点存在 fully clipped，需修复 |
| 13·评分报告 | QAAu9 | 保留逐题证据和建议；移除未交付笔记/计划/精讲操作与自动难点文案；禁止静态岗位达标结论、假总分/置信度 |
| 62/63·导航 | uV9HB/S7y7V | 复用现有导航与账户偏好，不改回旧宽顶栏 |

实现前在 Pen 校准上述稿件（保留旧版参考），补配置建议、预览编辑、题型输入、答题/点评、历史，以及空/加载/失败/保存冲突/资料不足/来源失效/低置信度状态；逐项读取与截图核查后才实现页面。当前已完成校准稿，页面对照与人工验收仍须分别记录。响应式检查 375/768/1024/1440，字体命中和视觉检查与 DOM 溢出检查分开报告。

## 7. 验证、迁移与交付

迁移只作用本项目库：实施时读取 `.env` 目标及当前 Alembic revision，不预设版本；执行前 pg_dump 可恢复备份及归档可读检查，隔离 DB upgrade/downgrade/upgrade，业务库执行后读回版本/接口；不启停外部 PostgreSQL/Redis。

确定规则、版本、幂等、租约、权限/撤权、来源、保存与主观输出门禁需要自动化测试。四格式 golden set 及真实模型 smoke 使用合成材料，按 PRD 指标报告；受控 provider 验证异常不等于真实模型质量。运行检查、curl、真实浏览器、Pen/截图和用户人工验收分别记录。

确认方案并冻结 FastAPI 契约后启用并行 subagent：后端拥有 practice 领域/API/迁移/测试；前端拥有 features/practice 和对应页面/测试；主 agent 管理生成 SDK、学习模式入口、Pen 校准、PRD/OpenSpec、集成与自审，避免共享文件重复编辑。不运行 Next.js 或 Docker build；Git commit/push/PR 仍须当轮授权。

## 2026-10-03 校准 Pen 映射

真实 Pen 文件保持原 10–13 稿，新稿使用当前全局导航、象牙白/阳光黄设计变量。

| 新稿 | 节点 | 本期状态 |
| --- | --- | --- |
| 68 创建 | xbNqR | 资料/通用、题型/数量、画像覆盖与摘要 |
| 69 配置确认 | XSxzn | 原配置与建议配置分别确认 |
| 70 预览 | l3ED2y | 编辑/删除/重新生成/开始 |
| 71 答题 | r9L60 | 非限时、五题示例、保存与逐题提交 |
| 72 点评 | GHDtW | 回答证据、置信度、再次作答/重评/反馈 |
| 73 报告 | Lv72m | 实际覆盖/未评分/评分版本/知识点结果 |
| 74 编辑 Dialog | upwA8 | 题干、选项、答案、规则、讲解、授权来源 |
| 75 五型控件 | wFEcZ | 单选/多选/判断、简答、文本编程 |
| 76 任务与异常 | KmP7H | 空/处理中/取消/资料不足/失效/冲突/失败 |

截图保存于 `docs/ui-design/evidence/practice/<node>.png`。已查看渲染截图，布局和控件可读；MCP Get 的部分缓存 bounds 仍报告 clipped，与截图结果不一致，不能据此宣称零布局诊断。以实际渲染截图和后续浏览器逐项核对分别提供证据。
