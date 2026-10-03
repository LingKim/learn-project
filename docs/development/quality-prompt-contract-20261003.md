# 本批冻结契约

用户已批准上一批 `parallel-next-batch-20261003.md` 推荐范围。基线 `a9aa5db`，本批独立集成分支 `codex/learn-quality-prompt-integration`。不迁移业务库、不变更主工作区、不推送/PR/部署。

## 公共 Python 边界

- `learning.result_sources.load_learning_result(session, owner_user_id, source_id, trace_id)`：唯一首期 source `learning_turn`，返回 `LearningResultSource`。身份含不可变 turn UUID、owner、trace IDs；正文仅用于加密快照构造，不作为管理员响应。三重关系、资料模式、成功、完整Trace、KB存活和期限均校验。候选片段还须由质量模块按当前文件/KB/处理版本权限逐项校验，不可仅凭此身份读取。
- `agent_runs.contracts.ManagedPromptSnapshot`：`protocol_version=1`，真实 AgentRun ID、根版本、固定 composition（version_id/key/slot/position/hash）、稳定场景和动态Schema hash、provider/model/参数、只含来源元数据的 context_sources。
- Prompt 模块提供 `runtime.freeze_practice_run(session, run, settings, output_schema) -> ManagedPromptSnapshot`，调用者已把真实 PracticeRun 加入同一入队事务。函数核验启用/已发布版本、固定依赖，创建 AgentRun 并把JSON快照放到 `run.input_snapshot['managed_prompt']`，不得保存正文。
- Prompt 模块提供 `runtime.load_practice_prompt(session, snapshot, settings) -> RenderedManagedPrompt`，仅按保存的不可变版本装配并核验hash，不查询活动指针/启停状态。输出 system_messages 仅短期在worker/provider内存使用；不写manifest/日志。重试沿用同一快照。
- 首个注册场景 `question_generator/practice_generate`，工具为空；输出稳定契约复用 `GeneratedQuestions`/五型 `QuestionSnapshot`，动态输出复用 `generation_schema(config)`。旧manifest键保留，额外运行元数据不包含正文。
- 管理员认证每模块基于 `current_user_model` 后检查 `user.role=='admin'`；所有敏感API no-store，角色拒绝发生在ID查找之前。Bodyless审计由各模块独立表记录固定action/outcome/actor/target/version/request_id/time，不接收任意正文payload。

## 配置与迁移

- Settings 已声明 `diagnostic_snapshot_keys: SecretStr`（JSON key_id→Fernet key）、`diagnostic_snapshot_active_key_id`；无合法密钥必须稳定拒绝正文保存/读取，禁止隐式随机密钥或明文fallback。`ai_quality_confirmation_days=7` 默认关闭等待期沿原规格。
- Root 唯一迁移owner：`20261003_05`公共AgentRun → `20261003_06`质量表 → `20261003_07`提示词表及AgentRun根版本外键。Agent只提供其表结构/迁移建议，禁止自己提交migrations文件。
- 使用独立临时测试DB与合成密钥/正文验证。普通Trace默认30天，案例至关闭90天且总180天，正文访问撤销/到期/关闭立即拒绝，7天内物理清除。
- 不提供管理员策略发布、用户文件下载、全文检索、真实用户合成评测、未注册场景或空Agent角色。回放模式是 `fts_only|vector_only|hybrid_only|without_rerank|full`，仅现有策略记录候选的离线对照，不能声称BM25或独立负载/因果实验。

## 四路独占与关口

质量后端：`ai_quality/**`、`api/ai_quality.py`、其tests和质量OpenSpec；提示词后端：`prompt_management/**`、`api/prompts.py`、其tests和Prompt OpenSpec。

质量UI：`features/ai-quality/**`、`app/ai-quality/**`、`app/admin/ai-quality/**`；Prompt UI：`features/prompt-management/**`、`app/admin/prompts/**`。Root负责learning入口、practice入队/worker/provider、Settings、main、models导入、迁移、导航、OpenAPI与生成SDK、依赖及集成文档。

两后端先实现真实routes及Pydantic schemas；真实curl权限矩阵通过→Root实际导出OpenAPI/生成SDK→前端开始业务API实现。前端可以先核对Pen/设计和状态，但不得伪造DTO或假接口。API形状与operation_id最终冻结以同一实际导出SDK提交为准，变动先通知Root。所有角色/字段和功能遵循各已批准 design，不自行追加产品功能。
