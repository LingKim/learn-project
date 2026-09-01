# Design：文档解析、索引与可验证检索

## 1. 实施边界

本变更交付从“已上传·待解析”到“可检索证据片段”的完整纵切：

```text
服务端校验成功
  → 创建处理任务
  → 下载受控原件
  → 提取原生正文并识别待 OCR 页面
  → 按需执行 PDF 页面级 OCR
  → LlamaIndex 受控节点转换与结构感知分块
  → LangChain 模型适配 → qwen3.7-text-embedding
  → PostgreSQL 全文索引 + Qdrant 隔离向量写入
  → PostgreSQL 原子发布活动解析版本
  → LlamaIndex Retriever 组合混合召回
  → qwen3-rerank
  → 返回来源片段
```

生成式问答是下一变更。本变更的检索 API 不调用生成模型。

## 2. 运行事实与依赖

- PostgreSQL 由项目外部管理；当前服务版本为 18.1。
- 项目不启用 PostgreSQL `vector` 扩展。PostgreSQL 继续保存正文、分块来源、权限、任务、活动版本、全文检索和 Trace。
- Qdrant 是独立运行依赖，保存可重建的向量点与索引。正式环境通过配置注入 HTTPS endpoint 与 API Key；应用启动不得隐式创建、删除或修改 collection schema。
- 本地开发由项目 Compose 管理锁定版本的单节点 Qdrant 和独立持久化卷；生产部署形态、复制数、存储和备份参数由环境配置，不把单节点开发配置冒充生产高可用。
- API 与 worker 通过项目 adapter 使用官方 `AsyncQdrantClient`；领域服务不得直接依赖 Qdrant SDK 模型。服务端镜像与 Python client 一起锁版本并验证兼容性，不使用漂移的 `latest`。
- PDF 统一使用 `pypdfium2`（PDFium）承担原生文字层提取、页面信息读取和 OCR 前页面渲染，不让业务解析链路直接依赖 `pypdf`。页面级 OCR 通过项目 `DocumentOcrProvider` 协议接入；具体 OCR 引擎、语言包、版本、部署方式、默认页数/像素/时限和质量阈值必须在编码前完成选型并锁定，不得由业务服务直接依赖引擎响应结构。现有上传校验中的 `pypdf` 迁移必须用损坏、加密、嵌入附件和资源限制回归测试证明安全门禁未降低后才能移除依赖。DOCX 引入专用 OOXML 解析依赖，避免自行不完整解释 WordprocessingML；Markdown 引入支持 AST/块级结构的解析依赖；TXT 使用现有 UTF-8 解码边界。
- LlamaIndex 用于把项目解析器产出的受控结构转换为带稳定来源元数据的节点，并承载索引与 Retriever 组合抽象；不使用其默认文件扫描、默认持久化目录或框架内权限过滤代替项目边界。
- 千问文本 Embedding 通过 LangChain 的模型适配层接入 OpenAI 兼容接口；Rerank 使用独立 DashScope provider。两者都位于项目 provider 接口之后，不让领域服务依赖框架对象或厂商响应结构。
- 本变更不创建生成式 Agent 图。LangGraph 在后续需要多节点业务编排的 OpenSpec 中落地；本变更的持久化 `BackgroundTask` 继续是解析任务事实源。

### 2.1 框架与领域边界

- LangChain 对外暴露项目定义的 Embedding provider 协议，不把 `Document`、Message 或回调对象写入领域模型。
- LlamaIndex 节点 ID 由项目稳定 chunk 身份派生，节点元数据只携带执行所需的非秘密引用；正文最终写入并读取自 `DocumentChunk`。
- PostgreSQL 必须先解析当前用户、知识库、文件和活动版本允许范围；该范围转成 Qdrant payload filter 后才能执行向量召回。Qdrant 命中返回 PostgreSQL 加载正文时再次复核当前权限与活动版本。LlamaIndex 负责组合已授权候选，不负责补救越权查询。
- 框架版本、节点转换策略和 Retriever 组合策略进入处理或检索策略版本，并纳入 Trace 和固定评测。

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
- 向量索引 profile、Qdrant collection schema 版本
- Rerank 配置版本
- 正文字符数、块数、图片数、未识别图片数
- 原生文本页数、OCR 页数、OCR 低质量页数和 OCR 策略版本
- `published_at`、失败码、创建和完成时间

一个 FileAsset 最多只有一个已发布活动版本。草稿版本不会进入普通检索。

### 3.3 `DocumentChunk`

至少包含：

- `processing_version_id`、`file_asset_id`、`user_id`
- 稳定块序号和内容摘要
- 受控正文
- `source_kind`、页码起止、段落起止、标题路径
- PostgreSQL 全文检索列
- 稳定 Qdrant point ID 与向量同步状态；不在 PostgreSQL 重复保存向量
- 软删除/清理所需状态

正文是用户敏感数据，不进入普通日志、错误详情或管理员接口。

### 3.4 `VectorIndexProfile`

不可变向量索引 profile 至少包含：

- Embedding provider、模型 ID、维度、距离策略和预处理语义版本；
- Qdrant collection 物理名称、collection schema 版本和命名向量名称；
- 创建、启用、停用状态与时间。

首期 profile 固定为 `qwen3.7-text-embedding`、1024 维和 Cosine。模型、维度、距离或语义不兼容变化创建新 profile 与独立 collection，不在同一 collection 混写。历史文件不静默全量重建；迁移期检索必须按活动处理版本所属 profile 分组查询并版本化融合，或在策略发布前明确阻止不兼容混用。

### 3.5 `RetrievalTrace`

每次检索创建一个不可变 Trace，至少包含：

- `trace_id`、`request_id`、`user_id`、`knowledge_base_id` 和可选文件范围 ID；
- 解析版本、Embedding 配置、融合策略、Rerank 配置和完整检索策略版本；
- 原始 Query 的不可逆摘要、字符数、语言等脱敏特征；普通 Trace 不保存 Query 正文；
- 关键词、向量、融合和 Rerank 各阶段的候选 chunk ID、排名、分数、过滤原因和数量；
- 最终返回 chunk ID、证据门禁结果、阶段耗时、总耗时和脱敏错误码；
- `occurred_at`、默认过期时间和是否被质量工单合法保留的状态。

Trace 不存文档正文、片段正文、向量、模型完整响应、预签名 URL 或 Key。候选正文仍以 `DocumentChunk` 权限为准，管理员不能因为拥有 Trace ID 绕过用户资料所有权。

### 3.6 Qdrant point 与 payload

- point ID 由稳定 chunk UUID 一一映射，重复 upsert 保持幂等。
- named dense vector 使用当前 profile 定义的 1024 维 Cosine 配置。
- payload 只包含 `user_id`、`file_asset_id`、`processing_version_id`、`chunk_id`、profile/schema 版本等最小不可读标识；`user_id` 建立 `keyword` tenant index，`file_asset_id` 与 `processing_version_id` 建立 UUID payload index，其他字段只有真实参与过滤时才建索引。
- payload 不保存正文、标题、文件名、知识库名、对象存储地址、Query、预签名 URL、Key 或模型响应。
- 不在 payload 固化 `knowledge_base_id`：同一用户跨知识库关联或移动时由 PostgreSQL 当前关系生成允许的活动版本范围，避免为关系变化重建向量。

## 4. 解析规则

### 4.1 PDF

- 按页优先提取原生文字层并保留 1-based 页码。页面具有达到质量门禁的原生正文时，不执行重复 OCR。
- 对无有效文字层，或正文低于可配置阈值且页面以扫描图像为主的页面执行 OCR；不能只凭 PDF 图片对象数量判定扫描页。
- 混合型 PDF 按原页序合并 `native_text` 与 `ocr` 页面结果。同一页只能选择一个最终正文来源，不得把原生文本和 OCR 重复内容同时入库。
- 每个页面结果记录 `source_kind=native_text|ocr`；OCR 页面同时记录 provider、策略版本和归一化质量信号。分块继承页码与来源，不能把 OCR 文本伪装成原生文字层。
- OCR 页面渲染受可配置页数、像素、DPI、并发、单页时限和单文件总时限约束；原始渲染图和 OCR 中间文件只用于当前草稿处理，成功、失败或取消后均须清理，不写普通日志或长期对象存储。
- OCR 后全文仍无有效正文时确定性失败 `DOCUMENT_OCR_NO_TEXT`；质量低于门禁时失败 `DOCUMENT_OCR_LOW_CONFIDENCE`；超出明确资源上限时失败 `DOCUMENT_OCR_LIMIT_EXCEEDED`。这些失败不得发布乱码或静默降级为可用。
- 检测仍未识别的内嵌图片并单独计数。完成页面 OCR 不表示已经理解图表、照片或示意图。
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

- 项目解析器先产出受控结构块，再由 LlamaIndex transformation 管线转换为节点；不得把原始对象存储目录交给通用目录读取器扫描。
- 优先使用标题、段落、列表、表格和代码块边界。
- 超长结构单元才按可配置目标长度二次切分，并保留可配置少量重叠。
- 不把表头与全部数据行分离；代码块尽量完整保留。
- 每个块继承最小可用标题路径和来源锚点。
- 目标长度、最大长度、重叠量、清洗规则和 token 计数器属于版本化策略参数，通过固定评测集调优，不作为不可修改常量散落在业务代码中。

## 6. Embedding 与向量索引

- 正式模型为 `qwen3.7-text-embedding`，维度 1024，距离为 Cosine。
- 正式 provider 通过 LangChain 模型适配调用千问，领域服务只依赖项目定义的异步 Embedding 协议；确定性测试 provider 不依赖 LangChain 网络调用。
- 单次批量不超过服务官方上限 20，并同时受可配置 token、超时和并发限制。
- 单元和集成测试使用确定性测试 provider；真实 provider 只从环境读取 `DASHSCOPE_API_KEY`。
- Qdrant collection 使用命名 dense vector、1024 维和 Cosine；collection 与 payload index 由显式初始化命令在导入前创建并校验，API/worker 只使用兼容 schema。
- 每批 upsert 使用稳定 point ID 和 `wait=true`，只在操作完成后核对处理版本预期点数；部分失败可幂等重试，不得在未完整写入时发布活动版本。
- 模型 ID、维度、距离或语义不兼容策略变化必须创建新解析版本和独立 `VectorIndexProfile`/collection，不得把不兼容向量混入同一 collection。
- Qdrant alias 只用于经过评测的整个 collection/profile 蓝绿切换，不承担单文件、单用户或单处理版本发布，也不与 PostgreSQL 形成原子事务。
- 只记录调用次数、耗时、批量大小、模型 ID、状态和脱敏错误码；不记录输入正文、向量或完整响应。

## 7. 混合检索与 Rerank

### 7.1 召回

- 关键词召回使用 PostgreSQL 全文检索，向量召回使用 Qdrant Cosine；本变更不把 BM25/全文检索迁入 Qdrant。
- 两路先各自取得已授权候选，再由 LlamaIndex Retriever 组合层使用版本化融合策略合并去重。
- PostgreSQL 先固定 `user_id`、有效 `KnowledgeBaseFile`、活动解析版本和可选文件集合；关键词 SQL 使用同一范围，向量查询把允许的 `user_id`、`processing_version_id` 和可选 `file_asset_id` 转成 Qdrant payload filter。
- Qdrant 只返回 point/chunk ID 与分数。系统回 PostgreSQL 通过当前有效关联和活动版本重新加载正文；并发删除、移动或版本切换导致复核失败时丢弃候选并按策略补查，不返回陈旧结果。
- Qdrant 不可用时，如果激活策略要求混合检索，接口明确失败；只有显式发布并通过评测的降级策略才能返回 BM25-only，禁止静默改变策略。
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
4. `ocr`（存在待 OCR 页面时）
5. `chunking`
6. `embedding`
7. `indexing`
8. `publishing`

无待 OCR 页面时跳过 `ocr`。OCR 和 Embedding 等可计数阶段分别返回已处理页数/总页数、已处理块数/总块数；无法准确计算进度时只返回阶段，不计算虚假线性百分比。

### 8.2 执行模型

- 领取任务使用 PostgreSQL `FOR UPDATE SKIP LOCKED`，领取和状态变更使用短事务。
- 下载、解析和模型调用在事务外执行；worker 定期续租。
- 每次领取生成不可复用的 `lease_token`，提交时同时校验任务租约、FileAsset generation 和解析版本状态，阻止旧 worker 发布结果。
- 未发布正文与块使用 PostgreSQL 草稿版本隔离，向量 point 以同一 `processing_version_id` 写入 Qdrant。检索允许范围只来自 PostgreSQL 活动版本，因此草稿 point 不可见。
- worker 完成全部 Qdrant upsert、等待确认并核对预期点数后，才在 PostgreSQL 短事务内校验租约、generation 与版本状态并切换活动版本。若 PostgreSQL 发布失败，Qdrant 草稿 point 成为不可见孤儿，由幂等清理任务回收。
- PostgreSQL 与 Qdrant 不宣称跨库 ACID；所有写入以稳定 point ID、持久化任务、可重试操作记录和周期对账达到最终收敛。

### 8.3 取消与重试

- `pending` 立即取消；处理中写入 `cancel_requested`，worker 在安全检查点停止；`publishing` 开始后拒绝取消。
- 取消清理本次草稿，原始文件保留；首次解析回到待解析，重新解析继续使用旧活动版本。
- 损坏、OCR 后空正文、OCR 低质量、结构不支持和内容超限不自动重试。
- 存储、PostgreSQL/Qdrant 连接、OCR 运行时短暂不可用、Embedding 限流、超时和可重试服务错误最多自动重试 3 次。
- 鉴权或配置错误直接最终失败并脱敏告警。
- 手动重试创建新任务/尝试，不覆盖历史记录。

## 9. 文件关联、移动与删除

- 同一用户多个知识库关联同一 FileAsset 时复用活动解析版本，不重复解析或生成向量。
- 移动 KnowledgeBaseFile 只改变检索归属；不重建解析版本。
- 删除或移动关联先在 PostgreSQL 事务中改变当前授权范围；后续 Qdrant filter 与返回前复核立即排除该知识库中的失效结果，不等待向量物理删除。
- FileAsset 最后一个有效关联消失时，同一 PostgreSQL 事务撤销活动版本并创建持久化向量清理任务。worker 按至少包含 `user_id` 的 `user_id + file_asset_id + processing_version_id` filter 删除 Qdrant points，成功后再收敛 PostgreSQL 派生数据；未来物理文件清理由现有任务继续保证。
- 周期对账比较 PostgreSQL 活动/待清理版本与 Qdrant point 计数，修复缺失点、草稿孤儿点和已撤权陈旧点；对账只处理明确版本范围，不执行无范围全库删除。
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

前端继续遵循：组件 → query/mutation options → feature `api.ts` → 共享协议层 → generated SDK。内容库页面增加真实阶段、PDF OCR 页数、图片未识别数量、OCR 低质量或资源超限等安全失败原因、取消、重试和重新解析；不新增问答页面、分块调试页或向量管理页。

## 11. 安全与隐私

- 文档正文、分块、向量和模型输入均为敏感用户数据。
- Qdrant payload 只保存最小不可读标识，不保存正文或文件名；Qdrant endpoint、API Key 和 collection 管理权限只通过配置或秘密管理系统注入，生产连接必须使用受保护网络与 TLS。
- Qdrant 在线存储使用独立 POSIX 持久卷；snapshot/backup 使用独立目标并执行真实恢复演练。collection snapshot 不包含 alias，恢复后必须按保存的 collection schema、payload index 与 alias 清单恢复，并以 PostgreSQL 活动版本重新对账。
- 管理员不得通过接口、任务页、日志或错误读取用户正文、文件内容或检索片段。
- 普通 Trace 只保存脱敏 Query 特征、候选 ID/排名/分数、版本、耗时和错误；管理员不得直接检索或读取 Trace。未来诊断台只能通过有效质量工单及用户授权获取限定快照。
- Markdown 不主动访问外部图片；解析器不得执行宏、脚本、外部关系或嵌入附件。
- 千问 Key 只从环境或秘密管理系统读取，禁止写入数据库、日志、API、evidence 或 Git。
- 生产用户在首次触发会把正文发送给千问的处理前必须已有可审计的 AI 处理确认；未确认时不得向外部模型发送正文，接口返回稳定的待确认错误，由前端展示一次性说明并记录用户选择。
- 真实 smoke 使用用户明确指定的测试文件；只报告路径、格式、大小、页数/图片计数、状态、耗时和质量指标，不保存正文、向量或完整服务响应。
- 正式生产前核对千问服务协议中的正文留存、训练使用和地域边界，并保留用户首次 AI 处理确认记录。

## 12. 验证策略

1. 解析器、结构块、锚点、状态机、版本切换和 provider 适配器单元测试。
2. 隔离 PostgreSQL 与隔离 Qdrant 集成测试，覆盖 collection/schema 初始化、payload index、租约续期、并发领取、旧租约提交、取消、重试、删除和跨用户隔离。
3. 确定性 Embedding/Rerank provider 完成四类合成文档的端到端自动化验证。
4. 固定评测集分别测量关键词、向量、混合和 Rerank 后指标，并执行 BM25-only、Vector-only、Hybrid-only、无 Rerank 和完整策略消融。
5. 使用 `.env` 中真实 Key、隔离 Qdrant collection 和外部测试文件执行千问 smoke；测试数据、point、collection 和任务精确清理。
6. 后端真实 curl 门禁通过后更新 OpenAPI、生成前端 client，再做内容库页面联调和隔离 Playwright E2E。
7. 执行 Qdrant 中断、鉴权失败、schema 不兼容、部分 upsert、发布失败、孤儿/缺失 point 对账和快照恢复后重建矩阵。
8. 执行 Ruff、mypy、pytest、Oxfmt、Oxlint、TypeScript、Vitest、OpenAPI 和 API 边界检查；不运行 Next.js build 或 Docker image build。
