## ADDED Requirements

### Requirement: Explicit practice configuration
系统 SHALL 在学习室提供非限时练习模式，支持资料或通用知识来源、五种题型、知识点/能力/难度/题量配置，并在用户确认配置后才生成题目。

#### Scenario: Confirm suggested configuration
- **WHEN** 用户填写需求并请求题目方案
- **THEN** 展示 AI 配置建议及来源摘要，不静默覆盖显式字段，不在确认前生成题目

#### Scenario: Unsupported later phase
- **WHEN** 用户进入本期刷题页面
- **THEN** 不呈现可用的正式计时测评、简历/JD、难点、笔记或计划操作，不伪造未实现模块

#### Scenario: Change source scope
- **WHEN** 用户切换资料/通用模式、知识库或文件范围
- **THEN** 新建题集上下文，原 revision/attempt 继续绑定原来源快照，不由后续配置覆写

#### Scenario: Accept or modify suggested plan
- **WHEN** 用户选择原配置、采纳 AI 推荐或自定义修改
- **THEN** 前两者匹配存储候选摘要确认，自定义修改使旧 plan 失效并取得新方案，不能自由覆写旧确认摘要

### Requirement: Field based profile context
系统 SHALL 按字段处理本次配置、所选资料上下文与默认画像优先级，固化有效值、来源与画像版本，禁止任务自动回写个人资料。

#### Scenario: Omitted and cleared values
- **WHEN** 请求省略岗位字段而显式清空技能
- **THEN** 岗位允许画像兜底，技能本次不兜底，用户原画像不变

#### Scenario: Insufficient general topic
- **WHEN** 通用模式缺少可出题主题或上下文
- **THEN** 指明必要输入缺失，不调用模型猜测用户事实

### Requirement: Grounded practice generation
系统 SHALL 只使用当前用户选定资料范围的活动证据生成资料题，记录检索 Trace、处理版本、模型与不可变 Prompt 清单；通用题及报告保留模型通用知识标记。

#### Scenario: No sufficient evidence
- **WHEN** 检索为空或模型无法从给定片段支持题目答案
- **THEN** 明确资料不足，不发布题集，不隐式转为通用知识

#### Scenario: Forged or stale source
- **WHEN** 引用不在本次证据中或来源在生成期间被删除、移动或切换活动版本
- **THEN** 阻止题集发布，不能返回失效原文或伪造引用

### Requirement: Validated editable question revisions
系统 SHALL 校验题型、数量、选项、答案、评分规则、去重和来源，在预览编辑、删除或重新生成时创建新的题集版本，保留旧版本。

#### Scenario: Invalid generated batch
- **WHEN** 模型输出有空答案、非法选项、重复题、数量不匹配或缺失评分规则
- **THEN** 整次生成失败，不把部分题目当作成功题集

#### Scenario: Edit answer consistency
- **WHEN** 用户修改题干、选项或答案规则
- **THEN** 完整校验后发布新 revision，不仅修改题干而沿用失效答案

#### Scenario: Existing attempt and empty preview
- **WHEN** 用户删除预览全部题目或编辑正在练习的题集
- **THEN** 零题预览不能开始，旧 attempt 保持其已开始版本，新编辑仅影响后续开始

#### Scenario: Regenerate confirmed revision
- **WHEN** 用户重新生成整组或单题
- **THEN** 绑定当前基准 revision，整组沿用已确认上下文与实际题量分布，单题保持题型难度；出题配置改变须重新方案确认，失败不替换旧版本

### Requirement: Saved private practice answers
系统 SHALL 支持本人答案暂存、历史恢复、逐题提交、提交后讲解和再次作答，已保存答案与题集快照不能被其他账号或旧版本写入覆盖。

#### Scenario: Refresh after acknowledged save
- **WHEN** 用户保存成功后刷新或从历史重新进入
- **THEN** 恢复同一题集版本、当前题和已保存答案，未确认写入不显示已保存

#### Scenario: Concurrent answer write
- **WHEN** 旧页面 version 保存到已更新 attempt
- **THEN** 返回稳定冲突并保留用户输入，不静默覆盖较新答案

#### Scenario: Try answer again
- **WHEN** 用户看完讲解后再次提交不同答案
- **THEN** 新建 submission，保留原回答及其点评

### Requirement: Deterministic objective grading
系统 SHALL 按版本化标准答案判客观题：单选唯一选项等值、多选集合完全匹配、判断布尔等值，不让模型替代确定规则。

#### Scenario: Reordered multiple choice
- **WHEN** 提交多选答案顺序不同但集合相同
- **THEN** 判定一致；只选择部分正确集合不得自动获得未声明的部分分

### Requirement: Explainable subjective grading
系统 SHALL 按已保存评分维度评价简答和文本编程，输出可核对回答证据、等级、缺失项、置信度及建议，仅在规则完整时输出数值分数。

#### Scenario: Invalid grading evidence
- **WHEN** 模型引用不存在于提交原文的回答、未知维度或越界分数
- **THEN** 拒绝保存点评并保留已保存 submission，以便明确重试

#### Scenario: Low confidence or code answer
- **WHEN** 主观点评置信度低于已确认阈值或题型是文本编程
- **THEN** 显示低置信度与重评操作，代码点评不声称实际编译或测试通过

### Requirement: Append only regrading and reports
系统 SHALL 使主观重评产生新版本并记录原因、模型、Prompt 与输入引用；报告按实际提交覆盖度和对应最新评分汇总，不自动重算历史。

#### Scenario: Latest grading fails
- **WHEN** 新答案评分或重评失败
- **THEN** 原提交和旧评分可追溯，失败状态明确，不将旧答案得分当作新答案点评

#### Scenario: Unanswered questions
- **WHEN** 用户完成包含未提交题目的练习
- **THEN** 明确显示未提交及覆盖信息，不隐式提交草稿，不生成缺少完整规则或覆盖的总分

#### Scenario: Knowledge point results
- **WHEN** 用户查看练习报告
- **THEN** 基于本次提交展示知识点掌握情况、错误原因和建议，样本不足或未评分单列，不推断长期画像或创建难点资产

#### Scenario: Completed attempt
- **WHEN** 已完成 attempt 被请求保存或提交新答案
- **THEN** 拒绝写入，重新练习创建新 attempt；本人仍可主观重评并查看旧版本和最新状态

### Requirement: Bounded idempotent practice runs
系统 SHALL 用 request_key、摘要、租约 token、有界超时和对象 version 保护配置建议、生成、提交和重评；模型操作持久化异步入队并立即返回 202 运行引用，practice-worker 在短事务外执行模型调用。

#### Scenario: Refresh or interrupted submission response
- **WHEN** 用户刷新练习页或提交响应前连接断开
- **THEN** 通过任务 ID 或本人 request_key 找回实际状态，后台任务不依赖请求连接存活，不假装已完成

#### Scenario: Read immutable asynchronous result
- **WHEN** 运行完成后其他操作已经更新当前题集或评分
- **THEN** 根据该 run 的 type/id/version 读取其实际发布的方案、题集或点评版本，不误取最新指针结果

#### Scenario: Cancel pending or processing run
- **WHEN** 用户取消尚未发布的任务
- **THEN** pending 立即取消，processing 在安全节点停止并丢弃未发布结果，已有题目、提交和评分保持可读

#### Scenario: Replay and retry
- **WHEN** 相同 key 重放相同输入或明确重试失败执行
- **THEN** 复用成功结果，执行中返回运行引用和冲突，失败可重试而不重复创建 submission；不同输入复用 key 返回冲突

#### Scenario: Expired run or deleted set
- **WHEN** 执行租约过期、服务重启或题集已删除
- **THEN** 界面可以查询有效失败/不可用状态，旧 token 不能迟到发布，明确重试仅针对仍合法资源

### Requirement: Source revocation and private history
系统 SHALL 在所有出题、评分、来源预览和历史接口检查当前所有权与来源有效性，私有正文不得向管理员或其他用户开放。

#### Scenario: Revoked historical source
- **WHEN** 历史题目的资料已删除、移动或重解析
- **THEN** 保留本人已保存题目、回答和点评，标记引用不可用且隐藏失效来源原文，不再用失效原文生成或评分

#### Scenario: Another user or administrator
- **WHEN** 非所有者请求题集、attempt、答案、grade 或 run 正文
- **THEN** 返回 404，不能推断或读取他人业务内容

### Requirement: Traceable feedback and contract boundary
系统 SHALL 记录本人题目与点评反馈、模型参数、Prompt/Schema 指纹及引用版本，复用统一响应与前端 feature API/Query 链路。

#### Scenario: Feedback toggled
- **WHEN** 本人设置或取消有帮助/无帮助
- **THEN** 幂等持久化选择，不自动改变评分、策略或创建质量工单

#### Scenario: Inspect execution
- **WHEN** 普通用户查看 run 或历史业务结果
- **THEN** 不返回系统 Prompt、密钥、上游原始异常或非授权 Trace 正文

### Requirement: Design fidelity and bounded quality evidence
系统 SHALL 在实现前校准 Pen 10–13 与当前导航，分别核验状态、布局、文案和交互，并以合成四格式 golden set 验证出题质量与权限。

#### Scenario: Design missing or incompatible
- **WHEN** 本期状态未有对应稿件或原稿包含未开放业务
- **THEN** 先在 Pen 补齐或报告不可读取，不猜测页面或宣称设计通过

#### Scenario: Quality verification
- **WHEN** 执行出题验收
- **THEN** 分别报告检索 Recall@5、来源完整率、结构成功率、引用定位率、资料不足拒绝率、实际样例分母及人工抽样；目标见 proposal，不用合成样例冒充生产验收
