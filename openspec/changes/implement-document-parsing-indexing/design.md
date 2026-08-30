# Design：文档解析、索引与可验证检索

## 1. 实施边界

本变更交付从“已上传·待解析”到“可检索证据片段”的完整纵切：

```text
服务端校验成功
  → 创建处理任务
  → 下载受控原件
  → 提取正文和来源结构
  → 结构感知分块
  → qwen3.7-text-embedding
  → PostgreSQL 全文索引 + pgvector
  → 原子发布解析版本
  → 混合召回
  → qwen3-rerank
  → 返回来源片段
```

生成式问答是下一变更。本变更的检索 API 不调用生成模型。

## 2. 运行事实与依赖

- PostgreSQL 由项目外部管理；当前服务版本为 18.1。
- 宿主已提供 `pgvector 0.8.2` 扩展文件，当前项目数据库尚未安装扩展。
- Alembic 迁移显式执行 `CREATE EXTENSION IF NOT EXISTS vector`。权限不足时迁移失败并给出管理员操作说明，应用启动不得自动创建扩展。
- PDF 继续使用 `pypdf`；DOCX 引入专用 OOXML 解析依赖，避免自行不完整解释 WordprocessingML；Markdown 引入支持 AST/块级结构的解析依赖；TXT 使用现有 UTF-8 解码边界。
- 千问文本 Embedding 优先使用 OpenAI 兼容接口；Rerank 使用 DashScope HTTP 接口。调用封装在独立 provider 中，不让领域服务依赖厂商响应结构。

## 3. 领域模型

### 3.1 `BackgroundTask`

轻量通用任务事实源，至少包含：

- `id`、`user_id`、`task_type`、`business_object_type`、`business_object_id`
- `status`：`pending | processing | cancel_requested | succeeded | failed | cancelled`
- `stage`、`completed_units`、`total_units`
- `attempt_count`、`max_attempts`、`next_attempt_at`
- `lease_owner`、`lease_token`、`lease_expires_at`
- `input_generation`、`result_reference`
- `last_error_code`、`retryable`
- 创建、开始、结束和取消请求时间

任务 payload 只存稳定 ID 和非敏感配置快照，不存正文、文件名、预签名 URL、Key 或向量。

### 3.2 `DocumentProcessingVersion`

属于用户级 `FileAsset`，而不是知识库关联。至少包含：

- `file_asset_id`、`version_number`、`status`
- 解析器名称与版本、分块策略版本
- Embedding provider、模型 ID、维度、距离策略
- Rerank 配置版本
- 正文字符数、块数、图片数、未识别图片数
- `published_at`、失败码、创建和完成时间

一个 FileAsset 最多只有一个已发布活动版本。草稿版本不会进入普通检索。

### 3.3 `DocumentChunk`

至少包含：

- `processing_version_id`、`file_asset_id`、`user_id`
- 稳定块序号和内容摘要
- 受控正文
- `source_kind`、页码起止、段落起止、标题路径
- PostgreSQL 全文检索列
- `vector(1024)` Embedding
- 软删除/清理所需状态

正文是用户敏感数据，不进入普通日志、错误详情或管理员接口。

### 3.4 `RetrievalTrace`

每次检索创建一个不可变 Trace，至少包含：

- `trace_id`、`request_id`、`user_id`、`knowledge_base_id` 和可选文件范围 ID；
- 解析版本、Embedding 配置、融合策略、Rerank 配置和完整检索策略版本；
- 原始 Query 的不可逆摘要、字符数、语言等脱敏特征；普通 Trace 不保存 Query 正文；
- 关键词、向量、融合和 Rerank 各阶段的候选 chunk ID、排名、分数、过滤原因和数量；
- 最终返回 chunk ID、证据门禁结果、阶段耗时、总耗时和脱敏错误码；
- `occurred_at`、默认过期时间和是否被质量工单合法保留的状态。

Trace 不存文档正文、片段正文、向量、模型完整响应、预签名 URL 或 Key。候选正文仍以 `DocumentChunk` 权限为准，管理员不能因为拥有 Trace ID 绕过用户资料所有权。

## 4. 解析规则

### 4.1 PDF

- 只解析有文字层的页面，保留 1-based 页码。
- 检测每页图片及总图片数，但不执行 OCR 或图片描述。
- 混合型 PDF 可以发布文字结果，并提示未识别图片数量。
- 全文无有效文本，或有效正文低于可配置最低阈值且页面以图片为主时，确定性失败 `DOCUMENT_OCR_REQUIRED`。
- 不将空白页、页眉页脚噪声或重复水印单独生成有效分块；具体去噪规则版本化。

### 4.2 DOCX

- 提取标题、普通段落、列表、表格文本和稳定文档顺序。
- 来源使用标题路径和段落范围，不伪造页码。
- 表格保留表头与相邻数据行关系，超长表格按行组拆分。
- 检测内嵌图片数量；不解析图片文字、批注、修订历史、嵌入附件和页眉页脚。

### 4.3 TXT

- 沿用 UTF-8/UTF-8 BOM、NUL 和字符上限校验。
- 按空行和段落结构形成基础块，保留段落范围。

### 4.4 Markdown

- 保留标题层级、段落、列表、表格和代码块边界。
- 图片只使用非空 alt 文本作为上下文并记录图片引用；不自动抓取远程 URL、相对路径或 data URI。
- HTML 块按不可信内容处理，不执行脚本或外部资源。

## 5. 分块策略

- 优先使用标题、段落、列表、表格和代码块边界。
- 超长结构单元才按可配置目标长度二次切分，并保留可配置少量重叠。
- 不把表头与全部数据行分离；代码块尽量完整保留。
- 每个块继承最小可用标题路径和来源锚点。
- 目标长度、最大长度、重叠量、清洗规则和 token 计数器属于版本化策略参数，通过固定评测集调优，不作为不可修改常量散落在业务代码中。

## 6. Embedding 与向量索引

- 正式模型为 `qwen3.7-text-embedding`，维度 1024，距离为 Cosine。
- 单次批量不超过服务官方上限 20，并同时受可配置 token、超时和并发限制。
- 单元和集成测试使用确定性测试 provider；真实 provider 只从环境读取 `DASHSCOPE_API_KEY`。
- 数据库使用 `vector(1024)`，HNSW 索引使用 Cosine 运算类；上线前以真实数据规模验证索引构建、召回和资源消耗。
- 模型 ID、维度或语义不兼容策略变化必须创建新解析版本，不得把新旧向量混入同一活动版本。
- 只记录调用次数、耗时、批量大小、模型 ID、状态和脱敏错误码；不记录输入正文、向量或完整响应。

## 7. 混合检索与 Rerank

### 7.1 召回

- 关键词召回使用 PostgreSQL 全文检索，向量召回使用 pgvector Cosine。
- 两路先各自取得候选，再使用版本化融合策略合并去重。
- 所有 SQL 在召回前固定 `user_id`、有效 `KnowledgeBaseFile`、活动解析版本和可选文件集合；不得先全局检索再在应用层过滤。
- 返回并记录基础混合召回排序，供质量评测和问题定位。

### 7.2 重排

- 使用 `qwen3-rerank` 对文本候选二次排序，不传图片或视频。
- 默认候选数量和 `top_n` 由配置及评测决定，初始基线可采用候选 40、返回 8，但不得写死为产品不可变规则。
- Rerank 失败时若当前发布策略要求 Rerank，接口明确失败，不静默返回未重排结果；测试或明确禁用 Rerank 的策略版本可以只返回基础混合召回。
- 指标分别记录混合召回和 Rerank 后结果，防止重排掩盖基础召回缺陷。

### 7.3 Trace 与诊断回放

- 检索入口在权限校验后生成 `trace_id`，贯穿 Query Embedding、关键词召回、向量召回、融合去重、Rerank、证据门禁和响应组装。
- 每阶段写入结构化诊断事件；治理写入失败不得把 Query 或正文降级写入普通日志。在线检索结果继续返回，但响应明确标记 Trace 不完整并产生脱敏运行告警。
- API 响应返回 `trace_id`，供未来用户质量工单绑定；不得向普通用户返回内部候选全集、其他文件 ID 或策略秘密。
- 普通 Trace 默认保存 30 天。绑定有效质量工单后只延长关联元数据保留期，正文授权快照由独立反馈变更管理；用户删除账号或源资料后不得通过 Trace 恢复正文。
- Prometheus 只记录阶段、结果类型和桶化耗时等低基数指标；`trace_id`、用户 ID、知识库 ID、文件 ID 和 Query 摘要不得作为 label。
- 诊断回放使用隔离 runner 和固定策略快照，不写活动索引、不改变线上发布指针、不创建用户可见回答。

固定评测集对同一 Query 运行：

1. BM25-only；
2. Vector-only；
3. Hybrid-only；
4. Hybrid + Rerank；
5. 明确需要时的无 Rerank 对照。

分别输出 Recall@K、MRR、nDCG、无答案判断、P95 延迟和错误率。候选的来源路由只能说明“由哪一路召回”；只有关闭某一路后的对照结果才能用于因果贡献判断。

## 8. 任务执行与一致性

### 8.1 状态和阶段

任务状态与用户可见阶段分离。解析阶段为：

1. `waiting`
2. `downloading`
3. `extracting`
4. `chunking`
5. `embedding`
6. `indexing`
7. `publishing`

无法准确计算进度时只返回阶段。Embedding 等可计数阶段返回已处理块数和总块数，不计算虚假线性百分比。

### 8.2 执行模型

- 领取任务使用 PostgreSQL `FOR UPDATE SKIP LOCKED`，领取和状态变更使用短事务。
- 下载、解析和模型调用在事务外执行；worker 定期续租。
- 每次领取生成不可复用的 `lease_token`，提交时同时校验任务租约、FileAsset generation 和解析版本状态，阻止旧 worker 发布结果。
- 未发布正文、块和向量使用草稿版本隔离；全部成功后在短事务内原子切换活动版本。

### 8.3 取消与重试

- `pending` 立即取消；处理中写入 `cancel_requested`，worker 在安全检查点停止；`publishing` 开始后拒绝取消。
- 取消清理本次草稿，原始文件保留；首次解析回到待解析，重新解析继续使用旧活动版本。
- 损坏、空正文、扫描 PDF、结构不支持和内容超限不自动重试。
- 存储、数据库连接、Embedding 限流、超时和可重试服务错误最多自动重试 3 次。
- 鉴权或配置错误直接最终失败并脱敏告警。
- 手动重试创建新任务/尝试，不覆盖历史记录。

## 9. 文件关联、移动与删除

- 同一用户多个知识库关联同一 FileAsset 时复用活动解析版本，不重复解析或生成向量。
- 移动 KnowledgeBaseFile 只改变检索归属；不重建解析版本。
- 删除关联后立即从该知识库检索范围消失。
- FileAsset 最后一个有效关联消失时，删除编排同时清理未发布任务、解析版本、块和向量；未来物理文件清理由现有任务继续保证。
- 跨用户即使物理 SHA-256 相同，也分别生成解析版本、正文块和向量。

## 10. API 与前端

计划接口：

| 方法与路径 | 行为 |
| --- | --- |
| `POST /api/v1/knowledge-bases/{kb}/files/{file}/processing-tasks` | 对失败、取消或已发布文件创建重试/重新解析任务；自动首次解析不依赖此接口 |
| `GET /api/v1/knowledge-bases/{kb}/files/{file}/processing-task` | 查询当前或最近任务、阶段、计数、错误和解析版本 |
| `DELETE /api/v1/knowledge-bases/{kb}/files/{file}/processing-task` | 请求取消待处理或处理中任务 |
| `POST /api/v1/knowledge-bases/{kb}/retrieval/search` | 在当前用户、单知识库和可选文件范围内返回证据片段及 `trace_id` |

普通 JSON 响应继续使用现有 `ApiResponse`/`PageResponse`、状态码枚举和 RFC 9457 Problem Details。OpenAPI 更新后重新生成只读前端 client。

前端继续遵循：组件 → query/mutation options → feature `api.ts` → 共享协议层 → generated SDK。内容库页面增加真实阶段、图片未识别数量、失败原因、取消、重试和重新解析；不新增问答页面、分块调试页或向量管理页。

## 11. 安全与隐私

- 文档正文、分块、向量和模型输入均为敏感用户数据。
- 管理员不得通过接口、任务页、日志或错误读取用户正文、文件内容或检索片段。
- 普通 Trace 只保存脱敏 Query 特征、候选 ID/排名/分数、版本、耗时和错误；管理员不得直接检索或读取 Trace。未来诊断台只能通过有效质量工单及用户授权获取限定快照。
- Markdown 不主动访问外部图片；解析器不得执行宏、脚本、外部关系或嵌入附件。
- 千问 Key 只从环境或秘密管理系统读取，禁止写入数据库、日志、API、evidence 或 Git。
- 生产用户在首次触发会把正文发送给千问的处理前必须已有可审计的 AI 处理确认；未确认时不得向外部模型发送正文，接口返回稳定的待确认错误，由前端展示一次性说明并记录用户选择。
- 真实 smoke 使用用户明确指定的测试文件；只报告路径、格式、大小、页数/图片计数、状态、耗时和质量指标，不保存正文、向量或完整服务响应。
- 正式生产前核对千问服务协议中的正文留存、训练使用和地域边界，并保留用户首次 AI 处理确认记录。

## 12. 验证策略

1. 解析器、结构块、锚点、状态机、版本切换和 provider 适配器单元测试。
2. 隔离 PostgreSQL 集成测试，覆盖 pgvector 迁移、租约续期、并发领取、旧租约提交、取消、重试、删除和跨用户隔离。
3. 确定性 Embedding/Rerank provider 完成四类合成文档的端到端自动化验证。
4. 固定评测集分别测量关键词、向量、混合和 Rerank 后指标，并执行 BM25-only、Vector-only、Hybrid-only、无 Rerank 和完整策略消融。
5. 使用 `.env` 中真实 Key 和外部测试文件执行隔离千问 smoke；测试数据和任务精确清理。
6. 后端真实 curl 门禁通过后更新 OpenAPI、生成前端 client，再做内容库页面联调和隔离 Playwright E2E。
7. 执行 Ruff、mypy、pytest、Oxfmt、Oxlint、TypeScript、Vitest、OpenAPI 和 API 边界检查；不运行 Next.js build 或 Docker image build。
