# hybrid-retrieval Specification

## Requirements

### Requirement：系统必须使用版本化文本 Embedding

系统 SHALL 通过项目 provider 接口和 LangChain 模型适配使用 `qwen3.7-text-embedding` 生成 1024 维向量，并将模型、维度、距离和策略版本固化到处理版本。

#### Scenario：真实 Embedding

- **WHEN** worker 对待发布分块生成正式向量
- **THEN** 请求使用配置的千问端点、模型 ID、1024 维和受控批量
- **AND** 当前用户已有可审计的 AI 处理确认
- **AND** Key 只从环境或秘密管理系统读取
- **AND** 日志不记录正文、向量或完整响应

#### Scenario：用户尚未确认外部 AI 处理

- **WHEN** 处理流程即将首次把该用户正文发送给千问，但没有有效确认记录
- **THEN** 系统不得发出外部模型请求
- **AND** 返回稳定 `AI_PROCESSING_CONSENT_REQUIRED` 状态供前端完成一次性说明与确认

#### Scenario：模型或维度变化

- **WHEN** 激活策略的模型 ID 或向量维度与旧版本不兼容
- **THEN** 系统创建新处理版本和对应索引数据
- **AND** 不把新旧向量混入同一活动版本

#### Scenario：自动化测试

- **WHEN** 单元或集成测试运行
- **THEN** 测试使用确定性 provider 返回固定维度向量
- **AND** 测试不依赖真实 Key、网络、额度或模型漂移

### Requirement：RAG 摄取与检索必须真实使用 LlamaIndex

系统 SHALL 使用 LlamaIndex 承担受控结构到节点的转换、索引抽象与 Retriever 组合，同时保持项目领域模型和 PostgreSQL 为正文、权限、向量与版本事实源。

#### Scenario：文档节点转换

- **WHEN** 项目解析器产出带来源锚点的受控结构块
- **THEN** LlamaIndex transformation 将其转换为稳定节点并保留页码、段落和标题路径
- **AND** 系统不使用通用目录扫描器读取未授权文件或目录

#### Scenario：组合已授权候选

- **WHEN** 关键词与向量查询已经在 SQL 中固定用户、知识库、文件和活动版本范围
- **THEN** LlamaIndex Retriever 组合层融合并去重这些已授权候选
- **AND** 不先执行跨范围全局检索再在应用层过滤

#### Scenario：框架持久化边界

- **WHEN** worker 发布处理版本或检索服务读取活动索引
- **THEN** 正文、分块、向量、发布指针和 Trace 来自项目 PostgreSQL 模型
- **AND** LlamaIndex 默认文档存储、默认向量存储或内存状态不成为业务事实源

### Requirement：混合召回必须在数据库查询前固定权限范围

系统 SHALL 使用 PostgreSQL 全文检索和 pgvector Cosine 分别召回候选，并在 SQL 中预先限定当前用户、单个有效知识库、活动处理版本和可选文件集合。

#### Scenario：知识库内检索

- **WHEN** 已认证用户在自己的知识库提交查询
- **THEN** 关键词和向量召回都只扫描该用户在该知识库中的有效文件关联
- **AND** 结果不包含已删除、未发布、失败或其他知识库的分块

#### Scenario：限定多个文件

- **WHEN** 用户提交属于当前知识库的文件 ID 子集
- **THEN** 两路召回都限定到该子集
- **AND** 包含无权或不属于该知识库的文件时返回不泄露响应

#### Scenario：管理员检索用户资料

- **WHEN** 管理员凭角色尝试检索普通用户知识库
- **THEN** 系统拒绝访问
- **AND** 管理权限不得绕过用户资料所有权

### Requirement：融合排序必须可复现并可评测

系统 SHALL 对关键词与向量候选执行版本化融合和去重，并保留基础混合排序用于质量报告。

#### Scenario：同一分块被两路命中

- **WHEN** 一个分块同时出现在关键词和向量候选中
- **THEN** 融合结果只保留一个分块
- **AND** 根据当前融合策略综合两路排名或分数

#### Scenario：评测基础召回

- **WHEN** 固定 golden set 执行
- **THEN** 结果记录关键词、向量和混合召回指标
- **AND** 后续 Rerank 结果不得覆盖基础召回证据

### Requirement：文本候选必须使用纯文本 Rerank

系统 SHALL 通过 provider 接口使用 `qwen3-rerank` 对混合候选文本重新排序，不得在本阶段使用 `qwen3-vl-rerank`。

#### Scenario：Rerank 成功

- **WHEN** 当前策略启用 Rerank 且千问返回合法排序
- **THEN** 系统按相关性返回配置数量的 Top-N 证据片段
- **AND** 每个结果保留文件、页码或段落、标题路径和排序分数

#### Scenario：Rerank 必需但失败

- **WHEN** 当前发布策略要求 Rerank 且调用最终失败
- **THEN** 检索接口返回明确服务错误
- **AND** 不静默把基础混合结果冒充为已重排结果

#### Scenario：测试策略禁用 Rerank

- **WHEN** 明确的测试或评测策略禁用 Rerank
- **THEN** 系统可以返回基础混合排序
- **AND** 响应和指标明确标识未执行 Rerank

### Requirement：检索 API 只返回证据，不生成回答

系统 SHALL 提供受保护的用户级检索接口，返回片段、排序信息和来源锚点；本变更不得调用生成模型或创建问答会话。

#### Scenario：有证据查询

- **WHEN** 查询在指定知识库中命中相关资料
- **THEN** 接口返回按最终策略排序的证据片段
- **AND** 不返回整篇文档、对象存储地址或其他用户信息

#### Scenario：无证据查询

- **WHEN** 召回和 Rerank 没有达到可配置最低证据阈值
- **THEN** 接口返回空证据集合或明确无充分证据状态
- **AND** 不编造片段、引用或 AI 回答

### Requirement：每次检索必须生成可回放的脱敏 Trace

系统 SHALL 为每次通过权限校验的检索生成 `trace_id`，记录解析/索引版本、检索策略版本、各召回通道、融合、Rerank、最终引用、耗时和错误的结构化元数据，同时不得把 Query 或片段正文写入普通 Trace。

#### Scenario：成功检索 Trace

- **WHEN** 用户检索自己的知识库并得到结果
- **THEN** 响应返回稳定 `trace_id`
- **AND** Trace 保存关键词、向量、融合和 Rerank 各阶段的候选 chunk ID、排名和分数变化
- **AND** Trace 保存最终引用、策略版本、阶段耗时和脱敏错误状态
- **AND** Trace 不保存 Query 正文、片段正文、向量、Key 或模型完整响应

#### Scenario：Trace 治理写入失败

- **WHEN** 在线检索已成功但部分 Trace 事件无法持久化
- **THEN** 系统不得把用户正文降级写入普通日志
- **AND** 检索响应明确标识 Trace 不完整并产生脱敏运行告警
- **AND** 不把不完整 Trace 冒充为可完整回放证据

#### Scenario：管理员凭 Trace ID 直接访问

- **WHEN** 管理员没有绑定质量工单和有效用户授权，仅持有 `trace_id`
- **THEN** 系统拒绝读取 Trace 和候选正文
- **AND** 管理角色不得绕过用户资料所有权

### Requirement：评测必须支持分阶段消融回放

系统 SHALL 对固定 golden set 支持 BM25-only、Vector-only、Hybrid-only、无 Rerank 和完整策略回放，分别计算质量、无答案判断、延迟和错误指标。

#### Scenario：执行消融评测

- **WHEN** 候选策略执行发布前评测
- **THEN** 报告分别包含各策略的 Recall@K、MRR、nDCG、无答案判断、P95 延迟和错误率
- **AND** 所有对照使用相同 Query、知识范围和目标相关性标注
- **AND** 回放不修改活动索引、线上策略指针或用户可见结果

#### Scenario：判断召回通道贡献

- **WHEN** 报告声明某一召回通道改善或损害质量
- **THEN** 结论必须来自关闭该通道的消融对照
- **AND** 不得仅凭候选来源路由宣称因果贡献

### Requirement：检索质量必须满足固定门禁

系统 SHALL 使用覆盖 PDF、DOCX、TXT、Markdown 的固定评测集验证精确词、同义表达和无答案查询。

#### Scenario：质量门禁

- **WHEN** 发布候选策略执行完整评测
- **THEN** 目标证据 `Recall@5` 不低于 90%
- **AND** 文件及页码/段落来源定位完整率为 100%
- **AND** 跨用户和跨知识库越权结果为 0
- **AND** 分别报告混合召回和 Rerank 后结果

#### Scenario：陈旧结果检查

- **WHEN** 文件被删除、移动或活动处理版本完成切换
- **THEN** 后续检索不返回已失效知识库归属或旧版本分块
- **AND** 自动化测试验证该行为
