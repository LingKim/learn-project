# Design：提示词工程化管理

## 1. 核心决策

提示词管理采用“代码定义能力边界，数据库管理可变指令”的模式：

```text
AgentRegistry（代码）
  ├─ agent_key / scene_key
  ├─ InputContextModel
  ├─ OutputModel
  ├─ contract_sha256
  ├─ allowed tools
  └─ executor
          ↓ 校验
PromptDefinition（稳定身份）
          ↓
PromptVersion（不可变内容）
  + PromptVersionDependency（固定公共片段）
          ↓ 预览与固定评测
发布活动版本
          ↓ 启动时固化
AgentRun（版本、模型、参数、输入/输出引用）
```

管理员可以改变已注册场景的指令内容，但不能通过数据库创造执行器、扩大工具权限、改写输出契约或新增任意代码路径。

## 2. Agent 与场景注册表

首期稳定 Agent key：

| Agent key | 职责 | 示例 scene key |
| --- | --- | --- |
| `flow_controller` | 意图识别与显式业务流程调度 | `learning_route`、`interview_route` |
| `content_analyzer` | 学习资料、简历和 JD 的结构化分析 | `document_summary`、`resume_analysis`、`job_analysis` |
| `question_generator` | 资料或画像约束下生成题目与评分规则 | `learning_quiz`、`interview_questions` |
| `interview_host` | 轮次式面试提问与追问 | `mock_interview_turn` |
| `evaluation_reviewer` | 答题、面试和复盘评分 | `assessment_review`、`interview_review` |
| `difficulty_tutor` | 薄弱点讲解、示例与练习 | `weakness_explanation` |
| `note_generator` | 按用户选择内容生成笔记预览 | `note_preview` |

表中 key 是未来稳定命名，不表示本变更立即实现全部场景。只有执行器和 Pydantic 契约已经存在的任务条目才进入运行时注册表和管理页；公共/Agent 片段由注册场景显式声明所需 key 和 slot，至少被一个真实场景依赖后才可纳管。注册表根据 InputContextModel、OutputModel 和工具声明生成稳定 `contract_sha256`，并在启动时校验重复 key、缺失 Schema、不合法工具声明和孤立片段；数据库出现未注册定义时只能读取历史，不能发布或启用。

## 3. 领域模型

### 3.1 `PromptDefinition`

- `id`、稳定 `definition_key`
- `agent_key`、`scene_key`
- `template_kind`：`shared | agent | task`
- `display_name`、`description`
- `runtime_status`：`enabled | disabled`
- `active_version_id`
- `created_at`、`updated_at`

唯一约束为 `agent_key + scene_key + template_kind`。共享片段使用受控 scene key，例如 `global_behavior`；它仍必须经过注册，不接受任意字符串命名。

### 3.2 `PromptVersion`

- `id`、`definition_id`、定义内整数 `version`
- `status`：`draft | published | retired`
- `content`、`content_sha256`
- `variables`：声明名称、类型、必填、最大长度、来源、敏感级别和显式默认值
- `change_description`
- `base_active_version_id`
- `rollback_from_version_id`
- `created_by`、`created_at`
- `published_by`、`published_at`

`definition_id + version` 唯一；同一定义仅允许一个 `published`。草稿可修改，每次修改重算内容哈希并使既有评测资格失效；发布和退役版本不可修改或删除。

### 3.3 `PromptVersionDependency`

- `root_version_id`
- `dependency_version_id`
- `slot`：`global | agent`
- `position`
- `dependency_sha256`

发布版本固定具体依赖，不保存“使用最新公共模板”的动态关系。数据库约束禁止循环依赖、重复槽位顺序和依赖草稿；第一版只允许任务模板依赖公共/Agent 模板，不开放任意深度依赖图。

### 3.4 `PromptEvaluationSuite`

- `id`、`agent_key`、`scene_key`、整数版本
- 合成 `cases`：变量、数据输入和预期断言
- 允许的模型配置范围、质量阈值和结构化输出断言
- `status`：`draft | published | retired`
- 创建、发布人和时间

评测集不保存生产用户内容。已发布评测集不可修改；更新样例产生新版本。

### 3.5 `PromptEvaluationRun`

- `prompt_version_id`、`evaluation_suite_id`
- `evaluation_fingerprint`
- 供应商、模型标识和参数快照
- 状态、逐样例结果引用、聚合指标、通过状态和失败原因
- 执行人、开始/结束时间、用量

指纹至少包含根内容哈希、依赖版本与哈希、输入/输出 `contract_sha256`、变量契约、评测集版本、模型标识和参数。任何组成变化都不能复用旧通过结果。

### 3.6 `AgentRun` 扩展

- `agent_key`、`scene_key`
- `root_prompt_version_id`
- `prompt_composition_snapshot`：版本 ID、slot、顺序和哈希，不含正文
- 输入/输出 `contract_sha256`
- 供应商、模型和参数快照
- `context_source_snapshot`：字段名、解析来源、业务对象 ID/版本或不可逆摘要，不含正文
- 输入上下文引用、输出业务对象引用
- 状态、耗时、用量、错误码和 request/trace ID

业务输出继续存入 Question、EvaluationReport、Note、LearningPlan 等领域对象并形成自己的版本。AgentRun 不保存完整渲染 Prompt，不取代业务正文的保留与删除规则。

## 4. 模板与消息装配

运行时按以下顺序构造消息，不把所有内容拼为一段自由文本：

1. 全局公共行为规则，作为受控 system 内容；
2. Agent 角色与职责规则，作为受控 system 内容；
3. 任务场景规则和代码生成的输出 Schema 说明；
4. 用户画像、资料、简历、JD、答案或转写，作为明确标注的不可信 data message 或 tool result；
5. 当前用户请求，作为 user message。

模板只解析 `{{variable_name}}` 形式的简单占位符。禁止属性遍历、过滤器、循环、条件、函数、文件 Include、环境变量访问和表达式求值。数组和对象由代码中的受控序列化器生成；正文长度、数组项目数和嵌套深度在进入模型前校验。

用户内容中的“忽略系统指令”“输出密钥”“调用某工具”等文本仅是数据。模型可见工具由执行器固定的 allowlist 决定，Prompt 无权增加工具；结构化结果必须通过 Pydantic OutputModel 校验，失败按业务场景的有限修复/重试规则处理。

### 4.1 个性化上下文解析

每个真实 Agent 场景在代码注册表中声明可消费字段、是否必填、允许来源和场景默认值。`ContextResolver` 在模板渲染前按字段执行以下顺序：

```text
request
  > selected_asset（本次选择的 Resume / JD 等）
  > weakness（本次选择且有证据的 Weakness）
  > profile（当前 UserProfile 快照）
  > default（场景注册的显式默认值）
```

`selected_asset` 与 `weakness` 在业务上都是本次明确选中的资产来源；二者具体可提供哪些字段由场景契约声明，不能互相覆盖不相关字段。解析器只用低优先级来源补充尚未决定的字段，不能以整个对象覆盖整个对象。

请求字段使用三态值：

- 字段省略：当前层没有决定，允许继续向低优先级来源查找；
- 字段显式非空：采用本次值并停止该字段兜底；
- 字段显式 `null`：记录本次禁用，停止该字段兜底并保持为空。

解析完成后，缺少必填字段则返回稳定字段列表或进入产品已定义的追问状态，不调用模型猜测。可选字段为空时只省略对应数据段，不生成“用户就是初级/没有薄弱点”等推断。

每个最终字段记录一个来源：`request | selected_asset | profile | weakness | default`。快照保存字段名、来源、UserProfile/Resume/JD/Weakness 的 ID 与版本或不可逆摘要；实际值仍由业务输入引用和保留策略管理，不复制进普通 AgentRun 日志。`UserProfile` 在 AgentRun 启动时读取一次并固化版本，运行中画像更新不改变当前任务。

上下文解析器是只读消费者。一次任务的值、模型输出和推断结果均无权调用画像更新；用户勾选“保存为默认画像”时，由业务页面在独立请求中调用个人资料 API，并携带明确字段集合和乐观锁版本。

## 5. 草稿、预览与评测

### 5.1 草稿

创建草稿时提交当前 `active_version_id` 作为基准。允许从活动版本、历史版本或空白初始内容创建；空白初始版本只能用于已经注册但尚无发布版本的真实场景。

### 5.2 本地预览

预览不调用模型，使用管理员输入的合成变量完成：

- 模板语法解析；
- 变量白名单、类型、必填、长度和默认值检查；
- 依赖顺序和哈希展示；
- 最终消息角色、内容长度和输出 Schema 摘要展示。

预览响应包含合成渲染结果，因此使用 `Cache-Control: no-store`，不进入浏览器持久缓存、前端埋点或普通日志。

### 5.3 在线固定评测

管理员显式发起评测，系统加载已发布合成评测集并使用实际配置模型。评测限并发、记录用量和稳定错误，不在每次保存草稿时自动消耗模型调用。

硬门禁包括全部样例可渲染、输出可通过 Schema、禁止字段未出现、引用/拒答等场景断言通过；质量阈值按 scene 的评测集定义。结果与完整指纹绑定。

## 6. 发布、回滚与停用

### 6.1 发布

发布在短事务中：

1. 锁定定义并读取当前活动版本；
2. 校验草稿的 `base_active_version_id` 仍等于当前值；
3. 校验注册表、依赖和最新有效通过评测；
4. 将旧发布版本转为 `retired`；
5. 将候选转为 `published` 并更新活动指针；
6. 写入不含正文的审计事件。

冲突返回 409 和稳定 `PROMPT_VERSION_CONFLICT`，不得自动覆盖或重新基于最新版发布。

### 6.2 回滚

管理员选择曾发布的目标版本、填写原因并提交当前活动版本 ID。系统复制目标正文、变量和依赖快照，分配新的递增版本并记录 `rollback_from_version_id`。若目标通过证据的完整指纹仍匹配当前模型与评测条件，可复用证据；否则先创建草稿并要求重新评测。历史版本不重新激活、不修改。

### 6.3 停用

停用是独立、可审计的安全开关，只影响新 AgentRun。新任务返回稳定不可用错误或由上层流程选择已确认的非 Agent 路径，不静默换 Prompt、模型或供应商。已运行任务继续使用固化快照；强制中止由业务任务状态机处理。

## 7. 内容复原语义

- **精确取回**：读取数据库中已保存的历史 Question、EvaluationReport、Note、LearningPlan 等版本，这是产品承诺的复原能力。
- **尽力重跑**：在输入仍存在、权限仍有效时，使用历史 Prompt 组合、模型参数和输入引用创建新 AgentRun 与新业务版本。
- **不可保证相同**：外部模型版本、供应商实现和非确定性可能变化，即使 temperature 为 0 也不能承诺字节一致。

历史来源已删除、用户权限已撤销或保留期已过时不得从日志、备份旁路或管理员 Prompt 页面恢复正文。

## 8. API 边界

计划管理员接口：

| 方法与路径 | 行为 |
| --- | --- |
| `GET /api/v1/admin/prompt-definitions` | 按 Agent、场景、类型、状态分页查询定义，不返回正文 |
| `GET /api/v1/admin/prompt-definitions/{id}` | 返回定义、活动版本摘要和注册契约摘要 |
| `GET /api/v1/admin/prompt-definitions/{id}/versions` | 返回版本时间线和评测状态，不返回正文 |
| `GET /api/v1/admin/prompt-versions/{id}` | 返回单版本正文、变量、依赖和评测摘要并记录敏感查看审计 |
| `POST /api/v1/admin/prompt-definitions/{id}/versions` | 基于活动或历史版本创建草稿 |
| `PATCH /api/v1/admin/prompt-versions/{id}` | 修改草稿正文、变量和变更说明 |
| `POST /api/v1/admin/prompt-versions/{id}/preview` | 使用合成数据完成无模型预览 |
| `POST /api/v1/admin/prompt-versions/{id}/evaluation-runs` | 显式执行固定模型评测 |
| `POST /api/v1/admin/prompt-versions/{id}/publish` | 携带基准活动版本原子发布 |
| `POST /api/v1/admin/prompt-definitions/{id}/rollbacks` | 从历史目标创建新版本并按门禁回滚 |
| `POST /api/v1/admin/prompt-definitions/{id}/status` | 启用或停用新任务入口 |

没有普通用户 Prompt API。所有响应复用现有 envelope、错误枚举和 RFC 9457；详情、预览和 Diff 响应设置 `Cache-Control: no-store`。

## 9. 前端信息架构

- 模板列表：Agent、场景、类型、启停状态、活动版本、发布时间和最近评测状态；
- 版本详情：正文编辑器、变量契约、依赖版本、变更说明、版本 Diff 和审计时间线；
- 预览：仅使用合成变量，展示消息角色和 Schema 摘要；
- 评测：样例状态、结构化输出结果、质量指标、用量和失败原因；
- 高风险动作：发布、回滚和停用使用明确确认，回滚必须填写原因并显示将产生的新版本号。

前端必须使用 feature API/Query 链路。Prompt 正文不写入 localStorage、sessionStorage、URL、错误上报、埋点或调试日志；离开未保存草稿时只提示，不在浏览器长期恢复正文。

## 10. 缓存策略

第一版直接以 PostgreSQL 为事实源并允许进程内短生命周期只读缓存。未来只有在观测到读取瓶颈后才引入 Redis：

- 正文缓存 key 包含不可变 `prompt_version_id + content_sha256`；
- 活动指针缓存独立短 TTL，发布、回滚和停用提交后失效；
- 缓存未命中回源数据库；Redis 不可用时不影响正确性；
- 不以启动预热作为唯一加载方式，不在 Redis 保存渲染后的用户 Prompt。

## 11. 安全与审计

- 管理员角色才可访问管理 API；普通用户、跨角色和未认证请求均不泄露定义是否存在。
- 读取正文、修改草稿、执行评测、发布、回滚、启停和拒绝访问均记录操作者、目标 ID、版本、结果、request ID 和时间，不记录正文。
- API 错误只返回稳定字段路径与错误码，不回显完整模板、变量值、用户数据或模型响应。
- 固定评测只用合成数据；评测结果正文按受控调试数据处理，不进入普通日志和浏览器缓存。
- 密钥仍由环境或秘密系统管理，不能成为 Prompt 变量、模板正文或管理 API 字段。

## 12. 验证策略

1. 模板解析器、变量契约、受控序列化、依赖顺序、循环拒绝和内容哈希单元测试。
2. PostgreSQL 集成测试覆盖定义唯一性、版本递增、不可变发布、并发冲突、活动版本唯一、回滚克隆和停用。
3. 使用合成固定评测验证结构化输出、陈旧指纹、模型错误、限流和不通过门禁。
4. 覆盖请求/资产/画像/薄弱点/默认值逐字段优先级、省略与显式 null、必填缺失、画像版本固化和禁止自动回写。
5. 使用恶意画像、简历/JD/薄弱点证据和资料片段验证其只作为数据，不能改变工具 allowlist、输出 Schema 或系统消息。
6. 管理员/普通用户 curl 权限矩阵通过后导出 OpenAPI，再生成前端 client。
7. 前端 Vitest 与隔离 Playwright 覆盖列表、编辑、Diff、预览、评测、发布、回滚、停用、no-store 和正文不持久化。
8. 自审普通日志、RFC 9457、审计、Prometheus、浏览器存储、URL 和质量工单不存在 Prompt/用户正文旁路。
