# Qdrant 向量存储迁移调研

> 调研日期：2026-08-30
>
> 调研范围：Qdrant collection、向量与 payload、过滤和索引、point 写删、alias、分布式一致性、副本、快照、Python 异步客户端、Docker 部署，以及 BM25、稀疏向量和混合查询。
>
> 证据边界：Qdrant 官方文档、官方 API 文档、`qdrant/qdrant` 与 `qdrant/qdrant-client` 官方仓库；未引用第三方博客，未启动 Qdrant、未做性能测试或故障恢复演练。
>
> 文档性质：从 PostgreSQL `pgvector` 切换至 Qdrant 的设计依据。实际变更仍须遵循 `PRD -> OpenSpec -> 实现 -> 自审 -> 自动化验证 -> 人工验收`。

## 结论

Qdrant 适合替代本项目尚未正式启用的 `pgvector`，但它应被定位为**可重建的向量点与向量索引服务**，不能取代 PostgreSQL 的正文、权限、知识库关系、任务状态、活动处理版本和 Trace 事实源。

推荐首期边界如下：

1. 每个不兼容的 Embedding profile 使用一个独立物理 collection；首期 profile 固定为 `qwen3.7-text-embedding`、1024 维、Cosine。
2. 同一 profile 的全部用户共享 collection，以 `user_id` payload 过滤隔离；为 `user_id` 建 `keyword` payload index 并设置 `is_tenant=true`，为其他高频 UUID 过滤字段建立对应 payload index。[1][2]
3. PostgreSQL 先解析当前用户允许访问的活动处理版本和可选文件范围，再把 `user_id`、`processing_version_id`、`file_asset_id` 转为 Qdrant filter；Qdrant 返回候选 ID 后，读取正文前再次由 PostgreSQL 复核权限与活动版本。
4. point ID 使用稳定 chunk UUID；批量 upsert 和清理使用幂等 API，并对需要立即发布的写入使用 `wait=true`。Qdrant 的写入完成与 PostgreSQL 提交之间没有跨库事务，必须保留可重试同步状态、补偿删除和对账任务。[3]
5. Qdrant alias 只用于**整个 collection/profile 的蓝绿切换**。它不能完成单个文件、单个用户或单个处理版本的原子发布；这些细粒度发布仍由 PostgreSQL 活动版本指针和 Qdrant payload filter 控制。[1]
6. 首期仍保留 PostgreSQL 全文检索。Qdrant 已原生支持稀疏向量、BM25 和 dense+sparse 混合查询，但 BM25 多租户 IDF、中文分词和融合策略需要独立 golden set 评测，不应随“向量库迁移”无证据地一并改写。[12][13][14][15]
7. 本地开发可由 Compose 管理锁版本的单节点 Qdrant 和独立持久卷；单节点 `replication_factor=1` 不具备高可用。生产必须另行确认存储、鉴权、TLS、副本、负载均衡、快照和恢复方案。[8][9]

## 项目事实与迁移边界

当前 `implement-document-parsing-indexing` 设计已经把以下职责留在 PostgreSQL：

- `DocumentProcessingVersion` 的活动发布状态；
- `DocumentChunk` 正文、来源结构和全文检索列；
- 用户、知识库、文件关联与当前权限；
- 后台任务、同步状态、检索 Trace 和质量评测证据。

Qdrant 只保存稳定 point ID、1024 维 dense vector 和最小不可读 payload。这个边界是合理的：Qdrant collection 是 points（vector + optional payload）的搜索单元，collection 内同一向量空间要求相同维度和距离；它不是本项目关系型权限与发布事务的替代品。[1][3]

因此，本次迁移不是“把 PostgreSQL 换掉”，而是：

```text
PostgreSQL + pgvector
  ↓
PostgreSQL（业务事实、正文、权限、活动版本、全文检索、Trace）
  + Qdrant（可重建 dense vector、过滤索引、向量召回）
```

## Collection 与多租户设计

### Collection 粒度

Qdrant 官方建议多数多租户场景使用单 collection 加 payload 分区，而不是每个租户一个 collection；大量 collection 会带来额外资源开销。官方给出的三种多租户方式是 payload 分区、每租户自定义 shard，以及两者结合的分层多租户。[1][2]

本项目首期推荐：

- 一个不兼容 `VectorIndexProfile` 对应一个物理 collection；
- 不按用户或知识库创建 collection；
- 不在一个 collection 内混写不同模型、维度、距离或不兼容预处理语义；
- collection 物理名包含 profile/schema 版本，例如 `document_chunks_qwen37_1024_cosine_v1`；
- 可选稳定 alias 指向当前 profile collection，但应用仍以 PostgreSQL 记录的 profile 选择 collection。

选择 profile 级 collection 的原因是，Qdrant 要求同一 dense 向量配置中的 points 具有一致维度和距离；named vectors 虽允许同一点保存多个不同向量空间，但不适合拿来隐藏不兼容模型的迁移生命周期。[1]

### Payload 与索引

首期 point payload 只保存：

| 字段 | 用途 | 建议索引 |
| --- | --- | --- |
| `user_id` | 强制租户隔离 | `keyword` + `is_tenant=true` |
| `file_asset_id` | 可选文件范围、清理 | UUID payload index |
| `processing_version_id` | 只检索 PostgreSQL 已发布的活动版本 | UUID payload index |
| `chunk_id` | 命中回表与一致性核对 | UUID payload index；若只按 point ID 回表，可经压测后省略 |
| `profile_schema_version` | 诊断和兼容性核验 | 只有真实作为 filter 时才建索引 |

不保存正文、标题、文件名、知识库名、对象存储地址、Query、预签名 URL、Key 或模型响应，也不固化 `knowledge_base_id`。知识库关联是 PostgreSQL 当前关系；固化到 payload 会让“同一用户跨知识库复用”和文件移动产生额外向量重写。

Qdrant payload index 用于加速过滤并估算过滤基数，帮助查询规划；官方明确说明索引会占用额外计算、内存和磁盘，只应为实际过滤字段建立。为 filterable HNSW，官方建议在导入数据前创建所需 payload index。[4]

`is_tenant=true` 从 Qdrant v1.11.0 可用。它不是权限机制，而是告诉 Qdrant 该字段代表租户，使相同租户的向量尽量共置，以改善顺序读性能；应用仍必须在每次查询中显式添加租户 filter。[2]

### 过滤的安全边界

Qdrant 支持 `must`、`should`、`must_not` 及 match/range 等 payload filter，并可把 filter 用于 query、scroll、delete 等操作。[5]

本项目不能先做全局向量检索再在应用层过滤。正确顺序是：

1. PostgreSQL 校验认证用户、知识库有效关联、活动处理版本和可选文件集合；
2. 构造至少包含 `user_id` 和允许 `processing_version_id` 的 Qdrant filter；
3. 在 Qdrant 内完成过滤向量召回；
4. 命中后回 PostgreSQL 读取正文，并再次复核当前关系和活动版本；
5. 并发删除、移动或版本切换导致复核失败时丢弃候选，并按已发布策略决定是否补查。

payload filter 是检索隔离执行手段，不是 Qdrant 自身可理解的业务授权。遗漏 `user_id` filter 会直接形成越权风险，因此客户端封装应让“授权范围”成为必填参数，并以跨用户负向测试作为门禁。

## 1024 维 Cosine 与向量 schema

Qdrant collection 创建时显式配置 dense vector 的 `size` 和 `distance`；同一向量空间内所有 points 必须具有相同维度和距离。Cosine 在 Qdrant 内部通过上传时自动归一化、再执行 dot product 实现。[1]

本项目应固定：

```json
{
  "vectors": {
    "dense": {
      "size": 1024,
      "distance": "Cosine"
    }
  }
}
```

Qdrant 不受 pgvector HNSW `vector` 类型 2,000 维上限约束。当前 v1.19.0 对应的官方服务端源码把 dense `VectorParams.size` 校验为 `1..=65536`；collection schema 声明的维度仍必须与写入、查询向量一致。选择 1024 维应由模型 profile、质量、延迟和存储评测决定，不能因为换库就任意提高维度；升级 Qdrant 后也应按锁定 tag 的源码/API schema 重新核对约束。[1][19]

模型 ID、维度、距离、归一化或预处理语义出现不兼容变化时，应创建新 profile 和新 collection。不要原地修改 schema 后混合新旧向量，也不要静默全量重建用户资料。

## Point upsert、删除与发布一致性

### Upsert

Qdrant point ID 支持 64 位无符号整数或 UUID。所有 API 包括 point loading 都是幂等的；默认 upsert 会插入不存在的 point，并覆盖相同 ID 的已有 point。[3]

这里的“覆盖”需要谨慎：整 point upsert 是整体替换，遗漏的 named vector 可能被置空；只更新某个 vector 或 payload 时应调用对应的局部更新 API，而不是把不完整 point 交给全量 upsert。[3]

因此稳定 chunk UUID 可直接作为 point ID：

- 相同处理版本重试不会生成重复 point；
- 重新解析必须生成新的 `processing_version_id` 和相应稳定 chunk 身份，避免覆盖仍在服务的旧版本；
- 只有草稿版本全部 point 写入并核对数量后，才能在 PostgreSQL 发布活动版本。

Qdrant point 修改先写 WAL，再异步应用。`wait=false` 或省略 `wait` 只返回 `acknowledged`，并不表示已经可检索，操作甚至仍可能最终失败；需要响应后立即检索或发布时必须使用 `wait=true`，等待 `completed`。[3]

### Delete

官方删除 API 支持按 point ID 集合或 payload filter 删除整个 points，也支持只删除某个 named vector 而保留 point。[3]

本项目推荐：

- 重解析成功发布后，旧版本 point 由持久化清理任务按 `processing_version_id` filter 删除；
- 文件最终删除时按 `user_id + file_asset_id` filter 清理；
- 所有 filter delete 必须同时包含 `user_id`，防止错误 ID 或过滤条件扩大影响范围；
- 删除失败不回滚已经生效的 PostgreSQL 权限撤销，旧向量即使暂留也必须被活动版本 filter 排除；
- 用对账任务扫描 PostgreSQL 期望 point 数与 Qdrant 实际 point 数，修复漏写和孤儿 point。

### 跨 PostgreSQL 与 Qdrant 的原子性

Qdrant 的 `wait=true`、幂等 upsert 和 WAL 都不能提供 PostgreSQL 与 Qdrant 之间的分布式事务。发布流程必须采用可恢复状态机：

```text
PostgreSQL 创建草稿处理版本
  → Qdrant 幂等 upsert（wait=true）
  → 核对预期 point 数/身份
  → PostgreSQL 单事务切换活动版本
  → 异步清理旧版本 point
```

若 Qdrant 写入失败，旧活动版本继续可用；若 PostgreSQL 发布失败，新 points 仍是不可见草稿并由补偿任务清理。检索 filter 只能包含 PostgreSQL 当前已发布版本，因此不会把“写入成功但发布失败”的向量暴露给用户。

## Alias 原子切换：能力与限制

Qdrant alias 是 collection 的附加名称，查询 alias 与查询实际 collection 相同。一个请求中的多项 alias action 原子执行，因此可以在后台构建新 collection 后，原子地删除旧映射并把 alias 指向新 collection，并发请求不会看到中间 alias 状态。[1]

但它有三项关键限制：

1. 原子边界是 Qdrant 内部的 collection alias action，不包含 PostgreSQL 状态、应用配置或其他外部系统。
2. alias 指向整个 collection，不能为单个用户、文件或 `processing_version_id` 切换。
3. collection 级 snapshot 不包含 aliases；迁移或恢复时必须单独备份和恢复 alias 映射。[1][10]

因此本项目使用方式应为：

- **可以**：不兼容 Embedding profile 完成全量、受控的蓝绿迁移后，切换 profile alias；
- **不可以**：每次文件重解析都新建 collection 并切 alias；
- **不可以**：把 alias 当作 PostgreSQL 活动处理版本指针；
- **不可以**：认为 alias 切换同时原子更新了 PostgreSQL `VectorIndexProfile`。

profile 级切换仍应先校验新 collection schema、点数、过滤隔离和固定评测集，再以 Qdrant alias action 和 PostgreSQL 策略发布组成可恢复的两阶段流程；任一步失败都要有明确的回滚或重试方向。官方 Embedding 模型迁移指南还要求在切换前处理 dual write，并指出 delete/partial update 需要暂停或另做同步；alias flip 本身不会把迁移期间的变更复制到新 collection。[20]

## 一致性、副本与可用性

### 单节点开发

单节点默认 `replication_factor=1`，没有额外副本。它适合本地开发和集成测试，不是高可用证明。[8]

首期单节点写入建议使用：

- 稳定 point ID；
- `wait=true`；
- 超时与有限重试；
- 处理版本点数核对；
- PostgreSQL 同步状态和周期对账。

### 分布式生产

Qdrant 使用 shard 水平拆分 collection，并用副本提高读吞吐和节点故障容忍。`replication_factor` 默认是 1；在自托管开源版中，创建 collection 后仅修改该配置不会自动创建或删除实际副本，必须显式管理 shard replica。Qdrant Cloud 才会按配置自动调整副本。[8]

Qdrant 默认偏向可用性和搜索吞吐。高并发更新同一 point 时，不同副本可能短暂出现不同状态。官方提供三组控制：[7]

- `write_consistency_factor`：多少副本确认后才返回，默认 1；提高会增强网络分区下的写确认，但需要更多副本在线；
- read consistency：`all`、`majority`、`quorum` 或指定副本数，默认 1；更强读一致性会增加读负载和延迟；
- write ordering：`weak`（默认）、`medium`、`strong`；`strong` 通过永久 leader 串行化写入，但 leader 不可用时写入也可能不可用。

这些设置不是“越强越好”。文档解析索引以稳定 point ID、单 writer/租约、`wait=true` 和版本化发布为主，应先做并发、节点故障与延迟测试，再决定生产副本数、写确认数和 ordering。不能用 `write_consistency_factor=1` 的成功响应声称所有副本已同步，也不能用强 ordering 替代应用层幂等和版本检查。

## Snapshot、备份与恢复

Qdrant collection snapshot 包含该 collection 的配置、points 和 payload，但不包含 aliases。分布式部署中，单个 snapshot 只包含创建它的节点上的数据，必须分别处理各节点 snapshot。[10]

恢复还有明确版本边界：snapshot 只能恢复到相同 minor 版本的同版或更高 patch，或下一个 minor 版本。例如 v1.18.1 snapshot 可恢复到不低于 v1.18.1 的 v1.18.x 或 v1.19.x。[10]

full storage snapshot 包含全存储及 aliases，但只适用于单节点；分布式模式不支持。full storage snapshot 只能在 Qdrant 启动时通过 CLI 恢复。[10]

官方支持把 snapshot 存到本地文件系统或 S3-compatible storage；但 Qdrant 在线数据目录需要可提供块级访问的 POSIX 文件系统，不支持把 NFS 或 S3/object storage 直接当作在线存储。[9][10]

对本项目的建议：

1. 本地 Compose 使用独立 named volume 挂载 `/qdrant/storage`，不要复用 RustFS 对象存储目录。
2. 正式环境把 collection snapshot 或平台 backup 纳入灾备；如使用现有 RustFS 作为 S3-compatible snapshot 目标，应使用独立 bucket、独立凭据并做真实恢复演练。
3. 保存 alias 清单、collection schema、payload index 初始化声明和应用 profile 配置；collection snapshot 本身不包含 alias。
4. PostgreSQL 备份与 Qdrant snapshot 没有跨系统一致性快照。恢复后按 PostgreSQL 活动版本重建/对账 Qdrant，不能假定两个备份时间点天然一致。
5. 向量可从 PostgreSQL chunk 与固定 Embedding profile 重建，但重建依赖模型仍可调用、语义版本未漂移且用户外部处理授权仍有效；“可重建”不等于“不需要备份”。

## Python 异步客户端

官方 `qdrant-client` 从 1.6.1 起提供 `AsyncQdrantClient`，方法与同步 `QdrantClient` 对齐；REST 和 gRPC 都支持异步模式。官方明确建议 FastAPI/ASGI Web 服务对 Qdrant 网络 I/O 使用异步 API，避免在 async handler 中执行阻塞调用。[6][11]

本项目应把客户端封装在基础设施 adapter 后：

- API 与 worker 使用 `AsyncQdrantClient`；
- 统一配置 endpoint、API Key、HTTPS、请求超时、gRPC/REST、有限重试和连接关闭；
- domain/service 不依赖 `qdrant_client.models`；
- adapter 暴露项目语义方法，例如 `upsert_processing_version`、`query_authorized_chunks`、`delete_processing_version`；
- 单元测试使用项目接口的 fake，集成测试才连接真实锁版本 Qdrant；
- 初始化命令负责创建/校验 collection 与 payload index，应用启动不得隐式改 schema。

版本必须在 `pyproject.toml`/lockfile 中精确锁定并随服务端版本一同验证。调研时官方 Python client 最新 release 为 v1.19.0，服务端官方最新 release 也是 v1.19.0；这只是 2026-08-30 的时间点事实，不应在实现中使用会漂移的 `latest`。[16][17]

## Docker 与版本锁定

Qdrant 官方 quickstart 和安装示例使用 `qdrant/qdrant` 或 `qdrant/qdrant:latest`，并挂载 `/qdrant/storage`；REST、gRPC 和集群端口分别为 6333、6334、6335。默认启动没有加密和认证，任何可访问网络的人都能访问实例。[9][18]

对本项目，示例中的 `latest` 只能作为官方快速开始语义，不能直接进入 Compose。实现时应：

- 锁定服务端 tag，例如调研时的 `qdrant/qdrant:v1.19.0`，受控拉取后再锁镜像 digest；
- 精确锁定 `qdrant-client` 并更新 Python lockfile；
- 使用独立持久卷；
- 本地只向需要的主机/容器网络暴露端口，不暴露 6335；
- 配置 API Key；正式环境使用 TLS 或可信反向代理/私网；
- 健康检查、资源上限、日志、监控、snapshot 和恢复演练分别纳入验证；
- 升级前核对 release notes、snapshot 恢复版本窗口和客户端兼容性，并执行备份与回滚演练。官方升级文档要求逐个 minor 升级、先更新客户端 SDK，并说明 SDK 只测试最近三个 minor 的向后兼容，不能跨多个 minor 直接跳跃。[21]

官方安装文档把 Docker 主要定位于开发/测试。若自行用 Docker/Compose 运行生产，还需要高性能持久存储、安全设置、多节点高可用、负载均衡、备份灾备以及监控日志；单个 Compose service 不满足这些条件。[9]

## 原生 BM25、稀疏向量与混合查询

### 能力事实

Qdrant 从 v1.7.0 起把 sparse vector 作为一等能力。一个 point 可以同时保存 named dense vector 和 named sparse vector；sparse vector 必须命名，距离固定为 Dot。[1]

Qdrant 当前原生 BM25 能力包括：[12][13]

- 服务端 `qdrant/bm25` inference：摄取和查询时直接传文本，Qdrant 生成并保存/使用 sparse vector；
- 也可由客户端 FastEmbed 生成 BM25 sparse vector；
- sparse vector 配置 `modifier: "idf"`；
- 可调 `k`、`b`、`avg_len`；
- ingestion 和 query 必须使用一致的 tokenizer、stemmer、stopwords 等文本处理参数；
- 默认是英语 stemming 和 stopword，非拉丁或无空格语言应使用 `multilingual` tokenizer；Qdrant v1.19.0 增加了语言中立处理建议；
- BM25F 当前没有原生支持，多字段需要多个 sparse vector 再通过 Query API 融合。

“支持服务端 BM25 inference”不能直接等同于“任意自托管镜像和部署配置已经验证可用”。官方 inference 总览对 self-hosted Qdrant 仍给出客户端 FastEmbed 路径；因此本项目若以后使用 `qdrant/bm25` 服务端 inference，必须先对锁定的自托管镜像做能力探针，否则采用客户端生成 sparse vector。[22]

需要区分两种“全文”能力：

- `text` payload index 提供词/短语存在性过滤，是 filter，不等同于按 BM25 相关性排序；[4][13]
- BM25 使用 sparse vector 和 IDF 进行相关性排序。[13]

Qdrant Query API 从 v1.10.0 支持 `prefetch` 多阶段/混合查询。dense 与 sparse 两路可在一个请求中召回，并通过 RRF 或 DBSF 融合；prefetch 还可以嵌套，并支持后续 rescoring/rerank 组合。Cosine 与 BM25 原始分数不在同一量纲，不应直接用固定 alpha 相加；分布式 collection 的全 shard 融合应放在顶层 main query，不能把 fusion 藏在 shard-local prefetch 中。[14][15]

### 多租户 BM25 的特殊边界

BM25 的 IDF 依赖语料统计。Qdrant 默认在被查询 shard 范围内计算；payload 多租户共享 shard 时，不同租户词表会混合，IDF 不再代表单租户内的稀有度。[2]

Qdrant v1.19.0 增加 `params.idf.corpus` filter，可把 IDF 语料限定到当前租户。该 filter 与检索 filter 独立；用于 IDF 的字段应创建 payload/tenant index。若 corpus filter 没有命中，Qdrant 不回退到 shard 全局 IDF，而会退化为没有稀有度信号的纯 TF 权重。自定义 shard 场景下，IDF corpus 也不会跨 shard 取数。[2]

这意味着若未来把 PostgreSQL 全文召回迁至 Qdrant BM25，每次查询至少要同时正确传递：

- retrieval filter：当前知识库/文件/活动版本允许范围；
- IDF corpus filter：至少当前 `user_id`；
- 与摄取一致的中文/多语言 tokenizer 和其他 BM25 参数。

遗漏其中任一项都可能产生隔离或排序质量问题。

### 对当前阶段的建议

**首期不要把 BM25 一并迁入 Qdrant。** 理由不是 Qdrant 不支持，而是当前 OpenSpec 已把 PostgreSQL 全文检索作为可审计基线，同时 Qdrant v1.19.0 的多租户 IDF 与多语言处理需要新的质量和运维决策。

后续若独立评估 Qdrant 原生 hybrid，至少建立以下对照：

1. PostgreSQL 全文 + Qdrant dense + 现有融合；
2. Qdrant BM25 sparse only；
3. Qdrant dense only；
4. Qdrant dense + BM25 sparse + RRF；
5. Qdrant dense + BM25 sparse + DBSF；
6. 上述混合召回再接 `qwen3-rerank`。

对同一授权范围与 golden set 测 Recall@K、MRR、nDCG、中文专名/编号精确命中、无答案判断、P95、错误率和租户隔离。只有新方案真实优于现有基线并完成中文 tokenizer、per-tenant IDF、snapshot 和回滚验证后，才通过新的 OpenSpec 改写关键词召回事实源。

## 实施前必须确认的门禁

1. collection/profile 命名、1024 维 Cosine schema 与显式初始化命令。
2. `user_id` tenant index 以及 `processing_version_id`、`file_asset_id` payload index 的真实过滤计划。
3. 跨用户、跨知识库、删除、移动、重解析和并发发布的负向矩阵。
4. upsert 部分失败、超时重试、`wait=true`、旧租约提交、补偿删除和孤儿 point 对账。
5. Qdrant 不可用、鉴权失败、schema 不兼容时的稳定脱敏错误；不得静默退化检索策略。
6. 锁版本 Docker 单节点持久化、重启和 collection snapshot 恢复演练。
7. 生产是否自托管；若自托管，明确节点数、shard 数、副本数、写确认、读一致性、ordering、负载均衡和备份责任人。
8. profile 蓝绿切换时 alias 与 PostgreSQL profile 状态的失败恢复流程。
9. 若未来启用 Qdrant BM25，独立验证中文 `multilingual` tokenizer、摄取/查询参数一致性和 `idf.corpus` 租户范围。

## 官方资料

1. [Qdrant：Collections](https://qdrant.tech/documentation/manage-data/collections/)
2. [Qdrant：Multitenancy](https://qdrant.tech/documentation/manage-data/multitenancy/)
3. [Qdrant：Points](https://qdrant.tech/documentation/manage-data/points/)
4. [Qdrant：Indexing](https://qdrant.tech/documentation/manage-data/indexing/)
5. [Qdrant：Filtering](https://qdrant.tech/documentation/search/filtering/)
6. [Qdrant：Async API for Python](https://qdrant.tech/documentation/tutorials-develop/async-api/)
7. [Qdrant：Consistency Guarantees](https://qdrant.tech/documentation/scaling/consistency-guarantees/)
8. [Qdrant：Distributed Deployment](https://qdrant.tech/documentation/scaling/distributed_deployment/)
9. [Qdrant：Installation](https://qdrant.tech/documentation/installation/)
10. [Qdrant：Snapshots](https://qdrant.tech/documentation/snapshots/)
11. [Qdrant 官方 Python Client 仓库](https://github.com/qdrant/qdrant-client)
12. [Qdrant：Server-side Inference - BM25](https://qdrant.tech/documentation/inference/inference-bm25/)
13. [Qdrant：Full-Text Search](https://qdrant.tech/documentation/search/text-search/full-text-search/)
14. [Qdrant：Hybrid Search](https://qdrant.tech/documentation/search/text-search/hybrid-search/)
15. [Qdrant：Hybrid and Multi-Stage Queries](https://qdrant.tech/documentation/search/hybrid-queries/)
16. [Qdrant Server 官方 Release：v1.19.0](https://github.com/qdrant/qdrant/releases/tag/v1.19.0)
17. [Qdrant Python Client 官方 Release：v1.19.0](https://github.com/qdrant/qdrant-client/releases/tag/v1.19.0)
18. [Qdrant：Local Quickstart](https://qdrant.tech/documentation/quickstart/)
19. [Qdrant 服务端源码：`VectorParams` 维度校验](https://github.com/qdrant/qdrant/blob/v1.19.0/lib/collection/src/operations/types.rs#L1413-L1468)
20. [Qdrant：Migrate to a New Embedding Model](https://qdrant.tech/documentation/tutorials-operations/embedding-model-migration/)
21. [Qdrant：Upgrades](https://qdrant.tech/documentation/upgrades/)
22. [Qdrant：Inference](https://qdrant.tech/documentation/inference/)
