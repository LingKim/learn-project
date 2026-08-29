# Tasks：实现后端文件上传、知识库文件管理与清理闭环

## 1. 规格与契约

- [x] 通过分轮决策树确认上传范围、文件限制、SHA-256 去重、删除、清理、隐私和后端优先边界
- [x] 将 PRD 更新为 v0.6，消除“MD5 是唯一身份”“病毒扫描已实现”“上传完成即 RAG 可用”等歧义
- [x] 创建 Proposal、Design 与三份增量 Specification
- [x] 自审 PRD、Proposal、Design、Specification 与 Tasks 的术语、状态、接口和非目标一致性
- [ ] 在 OpenSpec CLI 可用时执行 strict validate；当前环境缺少 CLI，不得误报已通过

## 2. 依赖、配置与存储初始化

- [x] 选择并引入 RustFS S3 兼容客户端及文件结构校验依赖，更新 `pyproject.toml` 和锁文件
- [x] 增加内部/公共 RustFS endpoint、凭据、region、bucket、签名时长、TLS/加密和任务配置，秘密使用 `SecretStr`
- [x] 更新 `.env.example`，只提供变量名、非秘密示例和安全说明
- [x] 实现幂等 `xuemian-ai-init-storage` 与 `make bootstrap-storage`，创建必需 bucket、最小 CORS 和生命周期规则
- [x] 扩展 readiness，检查对象存储客户端和必需 bucket；生产缺少安全配置时明确失败
- [x] 为 backend、worker、scheduler 定义独立启动命令；不管理宿主 PostgreSQL/Redis 生命周期

## 3. 数据模型与迁移

- [x] 实现 `UploadSession`、`StoredObject`、`FileAsset`、`KnowledgeBaseFile` 模型及状态约束
- [x] 实现 `FilePolicyVersion`、`FileAuditEvent`、`FileCleanupTask`、孤儿候选和幂等记录模型
- [x] 创建 Alembic 迁移、部分唯一索引、外键、CHECK、幂等和摘要唯一约束
- [x] 增加模型结构测试，确认公共 Mixin 只组合真实需要的字段
- [x] 在隔离数据库验证 upgrade，并按项目安全边界记录迁移验证证据

## 4. 文件策略与验证

- [x] 实现版本化默认策略、硬上限、草稿修改和原子发布用例
- [x] 实现普通用户读取有效策略与管理员版本管理接口
- [x] 实现文件名 NFC 规范化、路径/控制字符清理、255 字节限制和扩展名保护
- [x] 实现 PDF 签名、损坏、加密、嵌入附件与页数校验
- [x] 实现 DOCX OOXML 结构、宏、压缩比、解压量、字符数与段落数校验
- [x] 实现 TXT/MD 编码、NUL 字节、字符数和空内容校验
- [x] 实现服务端流式 SHA-256；客户端 MD5/SHA-256 仅作为不可信会话元数据
- [x] 增加白名单、边界值、伪装格式、损坏/加密和拒绝清理测试；不实现或声称病毒扫描

## 5. 上传会话与对象存储

- [x] 实现业务范围内的知识库上传会话创建、策略快照、容量/并发/频率限制和 24 小时幂等键
- [x] 实现不超过 20 MB 单次 PUT、超过 20 MB multipart、分片按需签名和有效会话续签
- [x] 实现完成、查询、取消、过期和 `DUPLICATE_ACTION_REQUIRED` 状态机
- [x] 实现 quarantine 流式验证、摘要锁、正式对象提升、同域物理去重和失败补偿
- [x] 实现关联、移动、取消重复候选；同知识库重复返回稳定 409，跨用户不泄露命中
- [ ] 增加完成重放、并发相同摘要、分片重复/缺失、签名过期、会话过期和 RustFS 故障测试

## 6. 知识库与文件接口

- [x] 实现知识库分页列表、创建和重命名，所有查询默认排除软删除并校验所有权
- [x] 实现知识库删除影响预览、一次性 token 和“不得删除最后一个有效知识库”规则
- [x] 实现知识库文件分页、名称搜索、状态筛选和“已上传·待解析”准确状态
- [x] 实现关联级重命名、跨知识库原子移动和短期附件下载 URL
- [x] 实现文件删除影响预览、过期/陈旧 token、`SOURCE_ONLY`/`CASCADE` 与立即撤销访问
- [x] 确保业务响应不暴露 StoredObject、bucket、永久 key、全局引用数或其他用户数据
- [ ] 增加 401/403/404 隔离、管理员不可下载、重命名扩展名保护和分页测试

## 7. Worker、Scheduler 与一致性

- [x] 实现 PostgreSQL 持久化任务领取、租约、优先级、幂等状态转换和 `FOR UPDATE SKIP LOCKED`
- [x] 实现短暂故障最多 3 次、物理删除最多 8 次及最终失败/人工幂等重试
- [x] 实现删除前锁定 StoredObject、复核有效 FileAsset 引用、引用计数不一致时停止删除
- [x] 实现每天 02:30 到期/临时/失败任务调度及 PostgreSQL advisory lock
- [x] 实现每周日 03:30 分页对账、孤儿候选双次确认和 7 天保护期
- [x] 实现 `enqueue_user_file_cleanup(user_id)` 和知识库删除清理编排
- [x] 实现上传会话、任务、审计元数据保留任务和删除墓碑基础
- [ ] 增加 worker 重启恢复、多 worker 竞争、重复删除、对象已不存在、对象缺失和计数漂移测试

## 8. 审计、错误与 OpenAPI

- [x] 实现不含文件名、摘要、URL、对象 key 和正文的文件审计事件
- [x] 将新增 HTTP/业务状态加入集中状态码枚举，并通过 RFC 9457 返回稳定 `error_key`
- [x] 验证 HTTP status 与 body `code` 一致，失败不包装为 200
- [x] 更新 OpenAPI 测试，确保管理员策略接口不暴露用户文件正文或下载能力
- [x] curl 门禁通过后导出 OpenAPI、重新生成前端 SDK 并执行 `openapi:check` 与 `boundaries:check`
- [x] 不新增内容库前端页面、feature API、Query 或业务组件

## 9. 真实服务验收与交付

- [x] 创建不含固定凭据、摘要或预签名 URL 的 `scripts/curl-file-smoke.sh`
- [ ] 使用隔离测试数据验证 PDF、DOCX、TXT、MD 单次与 multipart 上传、续签、取消、过期和拒绝矩阵
- [ ] 验证同知识库重复、跨知识库关联/移动、跨用户隔离和幂等重放
- [ ] 验证知识库 CRUD、最后知识库保护、下载、删除影响、陈旧 token 和异步清理
- [ ] 注入 RustFS 故障，验证补偿、重试、最终失败、恢复后重试和对账保护
- [x] 执行 Ruff、mypy、pytest、OpenAPI/生成客户端一致性及 API 边界检查；本轮不运行 Next.js build 或 Playwright
- [x] 自审日志、秘密、存储权限、未跟踪文件、规格任务状态和实际 evidence
- [x] 用户已完成本地页面验收，并于本轮明确授权 commit、push
