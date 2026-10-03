## ADDED Requirements

### Requirement: Private learning conversations
系统 SHALL 提供当前用户私有的资料/通用会话，资料会话固定一个知识库与可选多个文件，支持分页历史、自动标题、重命名与软删除。

#### Scenario: Cross owner access
- **WHEN** 另一个用户访问会话或轮次
- **THEN** 返回 404，不泄露标题、内容或来源

#### Scenario: Switch modes
- **WHEN** 用户切换模式或知识范围
- **THEN** 建立新的会话上下文，不沿用无关输入与结果

### Requirement: Grounded structured answers
系统 SHALL 使用 qwen3.8-flash，资料回答仅引用本次检索范围的证据；通用回答标记模型通用知识；正文不进入日志和系统指令。

#### Scenario: Missing evidence
- **WHEN** 资料检索无充分证据或模型判定证据不足
- **THEN** 明确返回资料中未找到，不编造来源

#### Scenario: Invalid or revoked source
- **WHEN** 模型伪造引用或返回前来源删除、移动、活动版本变化
- **THEN** 拒绝发布该轮答案，隐藏已失效来源正文

### Requirement: Idempotent bounded execution
系统 SHALL 以幂等 key、问题摘要、会话锁和租约 token 保护回答执行，事务外调用模型，按有限时长结束失败。

#### Scenario: Retry or duplicate submit
- **WHEN** 同 key 同问题重复提交
- **THEN** 成功结果复用，运行中返回冲突，失败可重试；不同问题复用 key 稳定冲突

#### Scenario: Deleted conversation during generation
- **WHEN** 用户在生成期间删除会话
- **THEN** 后续提交不得恢复会话或发布答案

### Requirement: Traceable prompt and feedback
系统 SHALL 保存实际不可变 Prompt 组合、模型参数、Schema 指纹与检索 trace_id，提供本人回答反馈；普通接口不得暴露系统 Prompt。

#### Scenario: Inspect result
- **WHEN** 用户读取历史或反馈结果
- **THEN** 可读本人业务结果与引用，不返回系统 Prompt 或模型内部思考

### Requirement: Natural language keyword recall
系统 SHALL 对自然问句进行安全分词与 OR 关键词召回，保留 PostgreSQL 授权过滤与独立排序，记录新的检索策略版本。

#### Scenario: Question includes words absent from document
- **WHEN** 自然问句含“什么”等文档未出现词但包含目标关键词
- **THEN** 关键词通道仍可召回匹配片段，输入不得作为 tsquery 运算符执行

### Requirement: Explicit answer language
系统 SHALL 以请求语言 zh/en 决定回答语言，默认中文，并记录运行参数。英文资料不改变默认语言。

#### Scenario: English evidence with Chinese output
- **WHEN** 用户使用默认中文语言询问英文资料
- **THEN** 返回中文解释及原资料引用，不直接把整段英文当作答案

## 2026-10-03 后续规格

本首版请求语言、发送确认与完整响应的交互由 `../../../improve-learning-chat-streaming/specs/learning-chat-streaming/spec.md` 的新要求扩展/替换；显式API language仍兼容，省略时使用用户默认语言，首问无弹窗与学习consent门禁。
