# Tasks：实现提示词工程化管理

## 1. 规格与依赖

- [x] 更新 PRD 至 v0.10，收敛模板拆分、变量、画像兜底、版本、评测、回滚、复原和管理员查看边界
- [x] 完成 Proposal、Design、增量 Specification 与课件证据边界
- [x] 与 `implement-user-profile` 对齐 UserProfile/Weakness 分工、字段级优先级、省略/null 语义和禁止自动回写
- [ ] 确认首个真实 Agent 场景已经具备执行器、InputContextModel、OutputModel 和工具 allowlist
- [ ] 确认提示词管理与首个业务 Agent 变更的交付顺序，不创建未被业务使用的空模板

## 2. Agent 注册表与数据模型

- [ ] 实现 Agent/scene 注册表、重复 key 启动校验和 Schema/工具契约读取
- [ ] 创建 PromptDefinition、PromptVersion、PromptVersionDependency、PromptEvaluationSuite 和 PromptEvaluationRun Alembic 迁移
- [ ] 扩展 AgentRun 的 Prompt 组合、模型参数和输入/输出引用快照
- [ ] 增加定义唯一、版本递增、单活动发布版本、依赖合法性和不可变状态数据库约束

## 3. 模板、变量与安全装配

- [ ] 实现仅支持简单占位符的模板解析器，拒绝表达式、函数、路径遍历、Include 和脚本
- [ ] 实现变量白名单、类型、必填、长度、来源、敏感级别和显式默认值校验
- [ ] 实现公共规则、Agent 角色、任务场景和代码输出 Schema 的确定性消息装配
- [ ] 实现用户画像、资料、简历、JD、回答和转写的受控数据序列化与长度/深度限制
- [ ] 实现逐字段 ContextResolver：request > selected_asset/weakness > profile > default，并校验每个场景允许的来源
- [ ] 实现请求字段省略可兜底、显式 null 禁止兜底、必填缺失返回追问/稳定错误
- [ ] 固化 UserProfile、Resume、JD、Weakness 的 ID/版本与字段级来源，不复制业务正文
- [ ] 验证任务临时值、模型推断和 Agent 输出不能自动更新 UserProfile
- [ ] 验证用户数据不能扩大工具 allowlist、改写状态机或绕过 OutputModel

## 4. 草稿、预览与评测

- [ ] 实现从活动、历史或初始版本创建草稿及基准版本记录
- [ ] 实现草稿编辑、内容哈希、变量/依赖校验和版本 Diff
- [ ] 实现无模型合成预览和禁止缓存响应
- [ ] 实现版本化合成评测集与管理员显式在线评测
- [ ] 实现内容、依赖、Schema、评测集、模型和参数联合指纹及陈旧证据失效

## 5. 发布、回滚与停用

- [ ] 实现数据库锁、基准活动版本校验和单活动版本原子发布
- [ ] 实现已发布/退役版本不可修改、不可删除及稳定 409 冲突
- [ ] 实现从历史版本克隆新递增版本的回滚、原因必填和评测复用条件
- [ ] 实现定义启停安全开关，只影响新 AgentRun
- [ ] 实现发布、回滚或停用期间运行任务继续使用启动快照

## 6. 管理员 API 与前端

- [ ] 按 v0.10 需求更新 Pen 中的提示词列表与版本详情，补齐 Diff、合成预览、评测指纹、停用、回滚新版本和审计状态并保留页面证据
- [ ] 实现管理员定义列表、详情、版本时间线和正文详情 API
- [ ] 实现草稿、预览、评测、发布、回滚和启停 API
- [ ] 对正文、预览和 Diff 设置 `Cache-Control: no-store`，并实现敏感查看审计
- [ ] 后端 curl 管理员/普通用户权限矩阵通过后导出 OpenAPI 并生成只读前端 client
- [ ] 通过 feature `api.ts`、query/mutation options 和共享协议层实现管理页面
- [ ] 实现列表、版本详情、草稿编辑、Diff、变量、预览、评测、发布、回滚、停用和审计时间线

## 7. 运行接入与复原

- [ ] 在首个真实 Agent 场景接入活动版本解析和启动快照固化
- [ ] 确保发布、回滚和公共片段变更不改变已运行 AgentRun
- [ ] 将业务输出保存到对应版本化领域对象，历史读取不依赖模型重跑
- [ ] 实现权限与数据仍有效时的尽力重跑，新建 AgentRun 和新业务版本且不覆盖历史
- [ ] Redis 保持非必需；若性能证据要求缓存，按不可变版本 key 和活动指针失效规则实现

## 8. 自动化、安全与交付

- [ ] 覆盖变量、依赖、循环、哈希、并发发布、不可变、回滚、停用和陈旧评测测试
- [ ] 覆盖字段级优先级、选中资产、活动薄弱点、画像版本、省略/null、必填缺失和禁止自动回写测试
- [ ] 使用合成 Prompt Injection 载荷验证消息隔离、工具权限和输出 Schema
- [ ] 覆盖普通用户/管理员越权、正文 no-store、浏览器不持久化和审计不含正文
- [ ] 自审普通日志、错误、指标、URL、浏览器存储、质量工单和评测结果不存在 Prompt/用户正文泄露
- [ ] 运行 Ruff、mypy、pytest、Oxfmt、Oxlint、TypeScript、Vitest、OpenAPI 和 API 边界检查
- [ ] 更新 evidence，记录真实 Agent 接入、模型评测、curl 和浏览器验证边界
- [ ] 不运行 Next.js build 或 Docker image build；用户人工验收后再根据当轮授权决定是否 commit、push
