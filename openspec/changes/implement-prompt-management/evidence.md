# Evidence：提示词工程化管理

## 已确认事实

- 用户在 2026-08-30 提供课程第十一章 11.0–11.4 五份 PDF，要求仔细阅读并作为学面通AI提示词管理功能的参考。
- 五份 PDF 共 48 页，已完成逐页文本提取和页面渲染核对；用户随后确认全部采用推荐方案，并授权更新 PRD 和 OpenSpec。
- 当前 PRD 已规划 M8 提示词管理器、固定样例、版本、发布、回滚和 AgentRun 提示词版本记录，但业务代码中尚无 PromptDefinition、PromptVersion、管理 API 或 Prompt 运行装配器。
- 当前实际后端只有认证、统一响应/错误、日志、知识库与文件管理等领域；文档解析、RAG 诊断和业务 Agent 仍处于后续 OpenSpec 或未实现状态，因此本变更不得预建七套空 Agent 模板并声称已经接入运行。
- 当前 `User` 没有目标岗位、工作年限、岗位等级、技能、薄弱点或头像字段；用户已确认新增独立 `UserProfile`，并要求题目/面试任务本次显式输入优先、未填写时才使用默认画像。

## 课件来源

- `11.0 如何复原面试题与学习计划？搭建提示词管理体系.pdf`
- `11.1 高价值提示词深度解读：AI 智能体该遵循哪些行为准则？.pdf`
- `11.2 提示词怎么按场景拆？如何对不同功能的 Prompt 模板进行设计？.pdf`
- `11.3 提示词版本控制与回滚：版本如何规范管理？支撑版本回滚的数据表要怎么设计？.pdf`
- `11.4 提示词变量注入 - 从通用模板到个性化提示词.pdf`

以上文件位于用户提供的外置磁盘课程目录；项目不复制课件原文件，只在需求和规格中记录已确认的产品结论。

## 吸收的参考原则

- 系统 Prompt 应从硬编码文案升级为数据库持久化、分类、版本化、可追踪的运行资产。
- 按 Agent 单一职责和任务场景拆分，避免一个大提示词同时承担全部业务。
- 使用公共规则与专用模板复用稳定约束，并记录整数版本和变更说明。
- 通过变量注入适配用户岗位、能力、技能和薄弱点，缺失信息需要显式处理。
- 个性化上下文按字段解析：本次请求优先于本次选择的简历/JD/薄弱点，再优先于 UserProfile 和场景默认值；省略允许兜底，显式 null 禁止兜底。
- 系统薄弱点保留独立证据模型，任务临时值和模型推断不能自动回写 UserProfile；AgentRun 只记录字段级来源和对象版本引用。
- 运行记录必须关联 session/task、Prompt 版本和执行结果，便于定位与回退。
- AI 编码行为准则中的稳定优先、简单性、精准修改和验证闭环作为实施方法参考，不作为运行时业务功能。

## 未直接采用的教学示例

- 不引入 Hermes 作为必需中枢；项目继续使用 FastAPI、SQLAlchemy 和 PostgreSQL 实现领域能力，LangChain/LangGraph只承担实际需要的模型调用与编排。
- 不照搬单表 `prompt_templates`、`template_type`、`is_active` 和 `variables VARCHAR`；它们不足以表达不可变版本、依赖固定、发布并发、评测证据和运行快照。
- 不采用“公共模板更新一次，全部 Agent 自动同步最新内容”；这会破坏历史可复现性，发布版本必须固定公共依赖版本。
- 不把 Redis 启动预热作为正确性依赖；PostgreSQL 是唯一事实源，Redis 只能是有性能证据后的可丢失缓存。
- 不要求所有 Agent 一律返回 JSON；输出格式由每个场景的代码 OutputModel 决定，结构化场景必须通过 Schema，面向用户的流式文本按专用协议处理。
- 不把“过滤非法符号、转义特殊字符”视为 Prompt Injection 防护；本变更采用消息信任边界、变量白名单、受控序列化、工具 allowlist 和输出 Schema。
- 不把模型重跑称为历史内容的精确复原；精确复原依赖已保存业务版本，重跑只作为新版本和尽力复现。
- 课件中“GitHub 14 万星”等宣传性来源描述未在本轮核验，也未作为需求事实或验收依据。

## 当前验证边界

- 已更新 PRD 至 v0.10，并创建 Proposal、Design、Tasks、Evidence 和一份增量 Specification；同时与 `implement-user-profile` 的数据所有权和隐私边界对齐。
- 尚未实现数据库迁移、Agent 注册表、模板解析器、管理 API、管理页面、模型评测或真实 AgentRun 接入。
- 当前环境没有 OpenSpec CLI 可执行证据；只能执行规格结构检查、冲突词扫描和 `git diff --check`，这些不能冒充 strict validate。
- 本轮不运行 Next.js build、Docker build、后端测试、前端测试、真实 curl 或浏览器验收，因为只有需求和规格变更。


## 2026-10-03 本地实施核验补充

本机 `main@57629ef` 已有真实问答、练习与学习资产执行器和检索 Trace，原文“尚无真实业务 Agent”等表述属于历史记录，不代表当前基线。当前仍没有本变更的领域模型/API/页面。具体首批范围、公共契约、迁移顺序、文件归属与验收条件见本目录 `implementation-plan-20261003.md` 及 `docs/development/parallel-next-batch-20261003.md`；方案待用户批准，尚未开始本变更实现。

已修正文档的 OpenSpec delta 头及 Requirement/Scenario 标点解析格式，未改产品规则；当前 CLI strict validate 通过。原规格的 AgentRun“扩展”需落为实际新增模型并与既有持久任务绑定；受管场景、动态输出 Schema 与入队快照契约须在实施批准前同步设计/spec。不将解析通过当成功能交付。

## 2026-10-03 首个真实受管场景后端

本批仅接入既有 `question_generator/practice_generate` 执行边界和实际依赖的 `practice_global` 公共片段。没有注册未来七类角色，没有任意定义创建 API；管理员 CLI `python -m xuemian_ai.prompt_management.cli --admin-user-id <UUID>` 校验真实管理员后，只从旧代码指令初始化 DRAFT。无已发布活动版本时，新受管生成任务稳定返回 `PROMPT_RUNTIME_UNAVAILABLE`。旧队列兼容和业务入队/worker/provider 接口由独立集成分支接入。

六张领域表分别保存定义、不可变版本、固定依赖、固定合成评测集、真实评测运行和无正文审计。草稿保存校验 revision；发布/回滚/启停校验 expected_active_version_id，并在同事务锁定定义。回滚克隆新递增版本，只有完整指纹仍匹配的已通过证据可复用。数据库触发器由共享迁移 07 保护已发布/退役版本正文及依赖、已发布评测集。管理 API 所有成功和错误响应均 no-store，普通用户在对象 lookup 前被拒绝；正文、Diff、预览和状态变更留无正文审计。

模板只支持一次 `{{variable}}` 替换，变量仅 trusted `agent_key`、`scene_key`；表达式、Include、脚本及不合法花括号被拒绝。用户事实通过独立 JSON data message 输入，长度/深度受限，不能修改 system 变量或空工具 allowlist。ContextResolver 逐字段遵守 presence/null 语义；快照保留不可逆字段摘要、学习资产/薄弱点 ID/version、画像 version，不复制正文。

评测必须显式执行固定四个合成样例：五种题型、资料引用、证据不足、注入载荷。真实 API 调用实际 Qwen 提供者；测试通过显式注入合成 provider 走同一业务验证器，没有运行时假成功或自动发布旁路。联合指纹包括正文 hash、变量声明、固定依赖身份/hash/slot/position、稳定 InputContext/OutputModel/QuestionSnapshot/空工具契约、每样例动态题目 Schema、固定 suite ID/version/hash、provider/model/参数和公共片段测试所用固定任务夹具 hash。失败、超时或取消不产生通过资格；进程中断的 processing 评测可在期限后重新执行。

`freeze_practice_run()` 与真实 PracticeRun 同事务创建 AgentRun，整份重新赋值 JSONB input_snapshot；`load_practice_prompt()` 仅读取不可变版本/hash/依赖及保存快照，SQL 不读取 active/runtime_status，使用入队时保存的模型参数。后续发布、回滚、停用及 Settings 模型变更不改变旧任务。

验证：22 个纯单元测试通过，含非法嵌套花括号的红绿回归；后端全源 mypy 112 模块通过；模块/API/专属测试 Ruff 通过。6 个隔离 PostgreSQL 集成检查已在 root 创建的专属数据库 `xuemian_next_20261003_prompt_backend_test` 全部通过；合计 28 passed，耗时 2.72 秒。首次执行 27 passed/1 failed 揭示启停返回的 updated_at ORM 过期导致 MissingGreenlet，已增加显式 refresh 并完成红绿回归。本段不把真实外部模型评测、SDK/前端验收记为已通过。
