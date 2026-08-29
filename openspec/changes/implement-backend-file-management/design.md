# Design：后端文件上传、知识库文件管理与清理方案

## 1. 总体边界

```text
未来前端业务页面
  -> 业务 feature API / generated SDK
  -> 知识库文件 HTTP 路由
  -> 上传会话 / 知识库文件应用用例
  -> 文件策略、存储、审计、任务端口
  -> PostgreSQL + RustFS + Redis 限频

独立 scheduler
  -> 生成到期、重试、对账任务
  -> PostgreSQL 持久化任务

独立 worker
  -> 领取校验、提升、删除、补偿任务
  -> RustFS / PostgreSQL
```

后端是用途、权限、策略与状态的唯一事实源。公共能力封装在后端服务和端口中；外部 HTTP 接口保持业务范围，不提供允许客户端任意提交 `owner_user_id`、bucket、object key、保留期或安全等级的万能上传接口。

本变更只实现后端接口。OpenAPI 生成客户端作为契约产物同步，但不新增 React 页面、feature API、Query 或业务组件。

## 2. 状态模型

### 2.1 上传会话

```text
CREATED -> UPLOADING -> UPLOADED -> VERIFYING -> COMPLETED
    |          |             |           |
    +----------+-------------+-----------+-> FAILED / CANCELLED / EXPIRED
                                      |
                                      +-> DUPLICATE_ACTION_REQUIRED
```

- `FAILED` 保存稳定原因码和可重试属性，不保存原始异常或内容。
- `DUPLICATE_ACTION_REQUIRED` 只暴露当前用户自己的候选关联。
- 会话 24 小时过期；签名过期不等于会话过期，有效会话可以续签。

### 2.2 文件资产

```text
STAGED -> VALIDATING -> AVAILABLE -> DELETING -> DELETED
                    \-> REJECTED
```

首期 `AVAILABLE` 只表示存储与校验可用，不表示 RAG 可用。

### 2.3 知识库处理状态

```text
PENDING_PROCESSING -> PROCESSING -> SUCCEEDED / FAILED / CANCELLED
```

本变更只创建 `PENDING_PROCESSING`，接口映射为“已上传·待解析”。后续解析 OpenSpec 才允许进入 `PROCESSING` 或 `SUCCEEDED`。

## 3. 数据模型

### 3.1 `upload_sessions`

组合 UUID 主键和时间能力，不软删除。关键字段：

- `owner_user_id`、`knowledge_base_id`：由业务路由和当前用户确定；
- `policy_version_id`、`policy_snapshot`：创建时固化的不可变规则；
- `original_filename`、`declared_mime`、`declared_size`；
- 可选 `client_sha256`、`client_md5`，均不可信；
- `upload_mode`、`storage_domain`、`temporary_object_key`、S3 multipart upload ID；
- `status`、`failure_code`、`expires_at`、`completed_at`；
- `idempotency_key`、请求摘要；同一用户/接口/key 在有效窗口内唯一。

成功或过期会话元数据保留 90 天。客户端摘要随会话淘汰，不进入正式业务文件表。

### 3.2 `stored_objects`

表示不可直接暴露给用户的物理字节。关键字段：

- `storage_domain`、`sha256`、`byte_size` 构成兼容域内唯一身份；
- `detected_mime`、`object_key`、`status`、`reference_count`；
- `cleared_at`、`created_at`、`updated_at`。

`sha256` 保存 64 位小写十六进制。`object_key` 使用不可猜测标识，不包含用户 ID、用户名或原文件名。`reference_count` 是性能字段，未删除 `FileAsset` 才是权威引用事实。

### 3.3 `file_assets`

表示某个用户拥有的逻辑文件，组合主键、时间、操作人和软删除能力。关键字段：

- `owner_user_id`、`stored_object_id`、`purpose`；
- `original_filename`、`detected_mime`、`byte_size`；
- `validation_status`、`validation_failure_code`；
- `policy_version_id`、`created_from_upload_session_id`。

跨用户即使命中同一 `StoredObject`，也必须创建独立 `FileAsset`，不得共享权限或业务派生数据。

### 3.4 `knowledge_base_files`

表示知识库与文件资产的业务关联，组合主键、时间、操作人和软删除能力。关键字段：

- `knowledge_base_id`、`file_asset_id`；
- `display_name`；
- `processing_status`、`processing_failure_code`、`resource_version`。

有效关联对知识库与文件资产唯一。`display_name` 属于关联，同一资产在不同知识库可以显示不同名称。原始文件名不可修改。

### 3.5 `file_policy_versions`

保存草稿和已发布不可变版本，包括每种用途的扩展名、MIME、大小、PDF 页数、文本字符、DOCX 解压量/字符/段落、音频时长、用户并发、频率和存储限制。上传会话保存版本引用及限制快照。

### 3.6 `file_audit_events`

追加式记录创建上传、完成、关联、下载授权、移动、重命名、删除和物理清理。字段只包含操作者、动作、目标 ID、结果、原因码、request ID、IP 哈希和发生时间；不得保存文件名、内容、摘要、URL、bucket 或 object key。默认保留 180 天。

### 3.7 `file_cleanup_tasks` 与孤儿候选

任务字段包括任务类型、目标类型/ID、优先级、状态、尝试次数、下次执行时间、稳定错误码、锁定者和锁定到期时间。任务幂等键防止重复创建同一清理工作。

孤儿候选记录首次/最近发现时间和确认次数；只有连续两次确认且至少存在 7 天才允许生成物理删除任务。

## 4. 对象存储布局与配置

存储域至少分为：

- `quarantine`：刚上传或待校验对象；
- `documents`：知识库、简历和 JD 长期原件；
- `recordings`：有独立到期策略的录音；
- `temporary`：上传分片、导出与其他短期对象。

storage bootstrap 按已确认基础设施契约初始化四类存储域及各自最小生命周期/CORS 边界；本变更的知识库上传实际只在 `quarantine` 与 `documents` 间流转。`recordings` 与 `temporary` 只提供存储域和策略基础，不创建未使用的录音、导出业务表或接口。

Settings 分离：

- `RUSTFS_INTERNAL_ENDPOINT`：后端 S3 操作；
- `RUSTFS_PUBLIC_ENDPOINT`：生成浏览器预签名 URL；
- Access Key、Secret Key 使用 `SecretStr`；
- region、bucket 名、签名时长、TLS/加密要求均来自配置。

本地公共 endpoint 可以是 `http://localhost:9000`；生产公共 endpoint 必须使用 HTTPS。上传 URL 默认 15 分钟，资料下载 URL 默认 5 分钟。签名不得写入日志。

显式、幂等的 `xuemian-ai-init-storage` / `make bootstrap-storage` 创建必需 bucket、最小 CORS 和生命周期配置。普通应用启动不得修改 bucket。readiness 检查客户端连接和必需 bucket；生产缺少要求的 TLS/静态加密配置时不得报告就绪。

## 5. 文件策略与默认限制

| 用途 | 白名单 | 默认 | 硬上限 |
| --- | --- | --- | --- |
| 知识库资料 | PDF、DOCX、TXT、MD | 50 MB；PDF 500 页；文本 200 万字符 | 100 MB；PDF 1000 页；文本 500 万字符 |
| 简历 | PDF、DOCX | 10 MB；文本 50 万字符 | 20 MB；文本 100 万字符 |
| JD | PDF、DOCX、TXT、MD | 10 MB；PDF 50 页或文本 50 万字符 | 20 MB；PDF 100 页或文本 100 万字符 |
| 真实面试录音 | MP3、M4A、WAV、WebM、OGG | 500 MB；180 分钟 | 1 GB；360 分钟 |
| 模拟面试录音 | WebM/Opus、M4A/AAC | 500 MB；60 分钟 | 1 GB；90 分钟 |

当前接口只接受知识库资料。未来用途的规则作为版本化契约存在，不提前创建对应业务模块。

稳定性默认值：每用户同时 3 个上传会话、每小时 30 个新会话、未完成上传 2 GB、长期文件 10 GB、短期录音 10 GB；系统硬上限分别为长期文件 50 GB、短期录音 50 GB。限额由数据库事实和 Redis 频率保护共同执行，Redis 故障时不得绕过创建频率限制。

## 6. 文件验证

验证在上传完成后由 worker 从 `quarantine` 流式读取：

1. 复核实际字节数并计算服务端 SHA-256。
2. 比较扩展名、声明 MIME、文件签名和允许策略。
3. PDF 校验结构、加密状态、嵌入附件、页数和损坏状态。
4. DOCX 必须为合法 OOXML ZIP，拒绝宏、异常压缩比和异常解压体积，并校验正文字符和段落数。
5. TXT/MD 必须满足允许编码、字符上限且不含 NUL 字节。
6. 校验失败将资产标为 `REJECTED` 并创建临时对象清理任务，不进入正式域。

首期不执行病毒扫描。文件默认作为附件下载，不在接口内执行宏、脚本或嵌入附件。

## 7. 上传接口与流程

所有业务 JSON 成功响应使用现有 `ApiResponse`，HTTP status 与 body `code` 一致；普通成功返回 200。RustFS 对预签名请求的响应不使用业务 envelope。

| 方法与路径 | 行为 |
| --- | --- |
| `POST /api/v1/knowledge-bases/{id}/file-upload-sessions` | 校验知识库所有权、策略、并发/容量与幂等键；创建绑定目标的上传会话并返回单次或 multipart 计划 |
| `POST /api/v1/file-upload-sessions/{id}/sign-parts` | 为有效 multipart 会话按需签发指定分片 URL |
| `POST /api/v1/file-upload-sessions/{id}/renew-upload-url` | 有效会话续签，不改变文件、用途或目标 |
| `POST /api/v1/file-upload-sessions/{id}/complete` | 提交单次完成或分片编号/ETag，幂等进入验证 |
| `GET /api/v1/file-upload-sessions/{id}` | 仅所有者查询会话、校验、重复处理和关联结果 |
| `DELETE /api/v1/file-upload-sessions/{id}` | 幂等取消未完成会话并生成临时对象清理 |
| `POST /api/v1/file-upload-sessions/{id}/duplicate-resolution` | 对当前用户自己的重复候选执行 `LINK`、`MOVE` 或 `CANCEL` |

不超过 20 MB 使用单次预签名 `PUT`；超过 20 MB 使用 16 MB multipart，客户端最多并发 3 个分片。ETag 只用于 S3 multipart 完成，不作为 MD5 或内容身份。

客户端可提交 SHA-256 进行本人资产预检；命中当前用户可信资产时可以不上传字节直接进入重复选择。未提供或未命中时必须上传并由服务端计算摘要。任何响应都不得泄露其他用户是否拥有相同摘要。

## 8. 知识库与文件接口

### 8.1 知识库

| 方法与路径 | 行为 |
| --- | --- |
| `GET /api/v1/knowledge-bases` | 分页列出当前用户有效知识库 |
| `POST /api/v1/knowledge-bases` | 创建非默认知识库 |
| `PATCH /api/v1/knowledge-bases/{id}` | 重命名自己的知识库 |
| `GET /api/v1/knowledge-bases/{id}/deletion-impact` | 返回影响快照和 5 分钟一次性确认 token |
| `DELETE /api/v1/knowledge-bases/{id}` | 携带 token 和删除模式；不得删除最后一个有效知识库 |

### 8.2 知识库文件

| 方法与路径 | 行为 |
| --- | --- |
| `GET /api/v1/knowledge-bases/{id}/files` | 使用统一 `PageResponse` 分页、名称搜索和状态筛选，默认创建时间倒序 |
| `PATCH /api/v1/knowledge-bases/{id}/files/{knowledge_file_id}` | 只修改当前关联的展示名称，不允许修改扩展名 |
| `POST /api/v1/knowledge-bases/{id}/files/{knowledge_file_id}/move` | 原子移动到另一个自己的知识库 |
| `GET /api/v1/knowledge-bases/{id}/files/{knowledge_file_id}/download-url` | 重新鉴权后返回 5 分钟附件下载 URL |
| `GET /api/v1/knowledge-bases/{id}/files/{knowledge_file_id}/deletion-impact` | 返回影响快照和 5 分钟一次性确认 token |
| `DELETE /api/v1/knowledge-bases/{id}/files/{knowledge_file_id}` | 携带 token 和 `SOURCE_ONLY`/`CASCADE`，立即撤销访问并入队清理 |

客户端以 `knowledge_file_id` 操作业务文件；上传阶段使用 `session_id`。不得暴露 `stored_object_id`、bucket、永久 object key、全局引用数或其他用户信息。

本变更不存在下游会话、题目、报告、笔记和难点，影响预览对这些类型返回零，但 token、资源版本和未来影响提供者契约必须真实可扩展。资源在预览后变化时返回 409 `DELETE_PREVIEW_STALE`。

## 9. 重复与并发

- 同一知识库存在相同有效文件时返回 409 `FILE_ALREADY_ATTACHED`。
- 同一用户其他知识库存在相同文件时进入 `DUPLICATE_ACTION_REQUIRED`，只允许关联、移动或取消。
- 跨用户可以命中兼容域内同一 `StoredObject`，但每个用户创建独立 `FileAsset`，响应不暴露跨用户命中。
- `stored_objects(storage_domain, sha256, byte_size)` 使用数据库唯一约束；并发完成时使用摘要级数据库锁或等价串行化。
- 创建会话接受 `Idempotency-Key`；同用户、同接口、同 key、相同请求体 24 小时返回原结果，不同请求体返回 409 `IDEMPOTENCY_KEY_REUSED`。
- 完成、取消、重复选择、移动和删除均幂等；重复完成不得重复增加引用。

## 10. 删除、任务与一致性

删除请求在数据库事务中：

1. 校验一次性 token、资源版本、所有权和删除模式。
2. 软删除业务关联并立即禁止列表、下载、解析和新任务引用。
3. 若用户资产已无有效业务关联，则软删除 `FileAsset`。
4. 锁定 `StoredObject` 并复核有效资产引用；只有最后一个引用消失时标记 `DELETING` 并创建物理删除任务。
5. 提交后由 worker 删除 RustFS；成功写入 `cleared_at`，对象已不存在视为幂等成功。

PostgreSQL 是任务事实源。worker 使用 `FOR UPDATE SKIP LOCKED` 或等价机制领取任务；scheduler 使用 PostgreSQL advisory lock 保证单一调度。Redis 不作为任务唯一事实源。

- 确定性验证失败不重试；
- 短暂 RustFS/数据库错误最多重试 3 次；
- 物理删除最多重试 8 次并逐步延长间隔；
- 超过上限进入最终失败和脱敏告警，人工只能重新执行幂等任务；
- 用户删除/账号清理优先于临时对象清理；
- 每天 `02:30 Asia/Shanghai` 生成到期、过期会话和失败清理任务；
- 每周日 `03:30 Asia/Shanghai` 分页对账；孤儿对象至少 7 天且连续两次确认后才删除。

提供 `enqueue_user_file_cleanup(user_id)` 应用用例，软删除该用户全部知识库文件关联和文件资产、撤销会话与下载能力并生成清理任务。完整账号删除 HTTP 用例在后续变更中调用它，本变更不新增删号端点。

## 11. 文件策略接口

| 方法与路径 | 权限与行为 |
| --- | --- |
| `GET /api/v1/file-policies/effective` | 已认证用户读取当前生效规则，不包含系统秘密 |
| `GET /api/v1/admin/file-policy-versions` | 管理员分页查看版本元数据和规则 |
| `POST /api/v1/admin/file-policy-versions` | 管理员创建草稿，必须满足硬上限 |
| `PATCH /api/v1/admin/file-policy-versions/{id}` | 只修改未发布草稿 |
| `POST /api/v1/admin/file-policy-versions/{id}/publish` | 携带基准版本 ID 原子发布；冲突返回 409 |

已发布版本不可修改。配置变更只影响新会话；安全紧急禁用可以取消尚未完成的相关会话，但不得让既有有效文件自动失效。

## 12. 错误与响应

错误复用 RFC 9457 Problem Details 和集中状态码枚举。稳定 `error_key` 至少包括：

- `FILE_TYPE_NOT_ALLOWED`
- `FILE_TOO_LARGE`
- `FILE_STRUCTURE_INVALID`
- `FILE_ENCRYPTED`
- `FILE_ALREADY_ATTACHED`
- `FILE_DUPLICATE_ACTION_REQUIRED`
- `FILE_UPLOAD_SESSION_EXPIRED`
- `FILE_UPLOAD_STATE_CONFLICT`
- `FILE_POLICY_VERSION_CONFLICT`
- `FILE_CAPACITY_EXCEEDED`
- `FILE_RATE_LIMITED`
- `DELETE_PREVIEW_STALE`
- `IDEMPOTENCY_KEY_REUSED`
- `OBJECT_STORAGE_UNAVAILABLE`

文件过大使用 413；请求/规则校验使用 422；重复、状态、token 和幂等冲突使用 409；频率或容量限制使用 429；未认证、无权和不可暴露资源分别使用 401、403、404。不得用 HTTP 200 包装失败。

## 13. 安全、审计与保留

- 所有业务查询默认排除软删除记录；普通用户只能访问自己的知识库、文件和上传会话。
- 管理员可以管理策略和查看脱敏任务统计，但不能查看文件名、内容、下载地址或对象 key，也不能下载用户文件。
- 原文件名只存在受控数据库字段；普通日志和审计事件不记录文件名、摘要、URL 或对象 key。
- 生产上传/下载必须 HTTPS；对象存储使用实际验证的静态加密能力或受控私有存储。密钥只来自环境或秘密管理系统。
- 数据库与对象存储备份加密保留 30 天；恢复旧备份后必须先重放删除墓碑。
- 成功/过期上传会话及成功清理记录保留 90 天，最终失败任务和文件访问审计保留 180 天，策略历史长期保留。

## 14. 验证顺序

1. 模型、约束、状态机、策略、校验器和应用用例单元测试。
2. 隔离 PostgreSQL/Redis/RustFS 集成测试，覆盖迁移、唯一约束、幂等、并发摘要完成和最后引用删除。
3. 显式执行 storage bootstrap，启动真实 FastAPI、worker、scheduler，运行 curl 上传与文件管理矩阵。
4. 注入 RustFS 失败，验证补偿、重试、最终失败和对账保护。
5. curl 全部通过后导出 OpenAPI，重新生成前端 Client，执行 OpenAPI 一致性和 API 边界检查。
6. 执行 Ruff、mypy、pytest 及相关前端静态/契约检查；本轮不运行 Next.js build、Playwright 或内容库 UI 测试。
