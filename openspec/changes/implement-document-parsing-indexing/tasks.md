# Tasks：实现文档解析、索引与可验证检索

## 1. 规格与依赖

- [x] 更新 PRD 至 v0.8，固化解析、模型、图片、检索 Trace、反馈授权和管理员诊断边界
- [x] 完成 Proposal、Design、三份增量 Specification 与初始 evidence
- [x] 核对千问当前官方 Embedding/Rerank API、价格与限流，记录可漂移字段而不写入秘密
- [x] 更新 PRD 至 v0.11，确认 LangChain、LangGraph、LlamaIndex 的项目级真实使用要求与职责边界
- [x] 更新 PRD 至 v0.12，将向量存储决策由 pgvector 修订为 Qdrant，并补充权限过滤、双库发布、清理与恢复边界
- [ ] 通过包管理器增加 LlamaIndex、LangChain 千问兼容适配、DOCX、Markdown、Qdrant client 和必要分块依赖，更新锁文件

## 2. 数据库与任务骨架

- [ ] 创建解析、分块、通用任务、向量操作幂等记录所需的 Alembic 迁移；不得启用 `vector` 扩展
- [ ] 实现 `BackgroundTask` 领取、短事务、租约续期、lease token、取消和重试分类
- [ ] 实现 `DocumentProcessingVersion`、`DocumentChunk`、活动版本唯一约束，以及 Qdrant collection/profile/point 身份映射
- [ ] 实现 `RetrievalTrace`、阶段诊断事件、30 天默认保留和质量工单合法延长钩子
- [ ] 实现显式 Qdrant 初始化/校验命令，创建 1024 维 Cosine collection、`user_id` tenant index 与高频 UUID payload index；应用启动不得隐式改 schema
- [ ] 验证干净隔离数据库 upgrade/downgrade/upgrade，以及 Qdrant 不可用、未初始化、鉴权失败和 schema 不兼容行为

## 3. 文档解析与分块

- [ ] 实现项目解析结构到 LlamaIndex 节点的受控 transformation，稳定映射节点 ID、来源锚点和策略版本
- [ ] 实现 PDF 文本层、页码、图片计数、扫描/低正文失败和噪声边界
- [ ] 实现 DOCX 标题、段落、列表、表格、图片计数与不支持结构边界
- [ ] 实现 TXT 段落解析与 Markdown AST、代码块、表格、alt 文本和外部图片禁止抓取
- [ ] 实现结构感知分块、稳定来源锚点、内容摘要和策略版本
- [ ] 增加四类解析器、复杂结构、确定性失败和资源限制测试

## 4. Embedding、索引与版本发布

- [ ] 实现确定性测试 Embedding provider，以及经 LangChain 模型适配的千问 `qwen3.7-text-embedding` provider
- [ ] 实现 AI 处理确认记录、后端发送前门禁和前端一次性确认交互
- [ ] 实现 1024 维批量 Embedding、并发/超时/限流、脱敏日志和错误分类
- [ ] 实现草稿解析版本、Qdrant `wait=true` 幂等 upsert/计数校验、PostgreSQL 活动版本原子发布与旧租约拒绝提交
- [ ] 实现首次解析、重新解析、失败保留旧版、取消清理草稿和策略升级边界
- [ ] 实现同用户跨知识库复用、移动不重建、删除后立即退出检索、Qdrant 异步清理与周期对账

## 5. 混合检索与 Rerank

- [ ] 实现 PostgreSQL 全文检索和 Qdrant Cosine 向量召回
- [ ] 实现 PostgreSQL 授权范围解析、Qdrant payload 前置过滤、返回前 PostgreSQL 复核，以及 LlamaIndex Retriever 组合层的版本化融合与去重
- [ ] 实现确定性测试 Rerank provider 和千问 `qwen3-rerank` provider
- [ ] 实现基础混合排序与 Rerank 后排序分开记录，Rerank 必需策略失败时不静默降级
- [ ] 实现各阶段候选 ID/排名/分数、策略版本、耗时和错误的脱敏 Trace，禁止记录 Query/片段正文或高基数 Prometheus label
- [ ] 实现受保护检索 API、`trace_id`、稳定响应模型、分页/Top-N 边界和 RFC 9457 错误

## 6. 前端联调

- [ ] 导出 OpenAPI 并重新生成只读前端 client
- [ ] 在 file-management feature API、query/mutation options 中接入任务查询、取消、重试、重新解析和检索契约
- [ ] 更新内容库文件状态、真实阶段、分块计数、图片未识别提示和安全失败原因
- [ ] 增加前端 API、Query、状态组件和交互测试；不新增问答或向量调试页面

## 7. 自动化与真实验证

- [ ] 建立不含用户原件的四类合成固定夹具和检索 golden set
- [ ] 验证 `Recall@5 ≥ 90%`、来源定位完整率 100%、越权结果为 0，并分别报告混合与 Rerank 后指标
- [ ] 执行 BM25-only、Vector-only、Hybrid-only、无 Rerank 和完整策略消融，报告 Recall@K、MRR、nDCG、无答案判断、P95 延迟和错误率
- [ ] 保持 PostgreSQL 全文检索为首期关键词基线；Qdrant BM25/sparse/hybrid 的中文 tokenizer 与租户 IDF 另立 OpenSpec 后再评估
- [ ] 使用隔离 PostgreSQL、隔离 Qdrant 和确定性 provider 验证取消、重试、并发 worker、租约过期、原子切换、移动、删除、孤儿点与缺失点修复矩阵
- [ ] 增加架构边界测试，证明 LangChain 与 LlamaIndex 进入真实链路且不会接管领域持久化、绕过 PostgreSQL 授权范围/Qdrant payload filter 或扫描非授权目录
- [ ] 使用真实 PostgreSQL/Qdrant/RustFS/千问及用户指定 PDF、DOCX、Markdown 和生成 TXT 执行脱敏 smoke
- [ ] 验证 Qdrant 锁版本单节点持久化、重启、collection snapshot 恢复、alias 清单恢复和 PostgreSQL 活动版本对账；不冒充生产高可用
- [ ] 真实后端 curl 门禁通过后执行前端隔离 Playwright E2E，并清理临时数据、任务、向量和测试服务

## 8. 自审与交付

- [ ] 运行 Ruff、mypy、pytest、Oxfmt、Oxlint、TypeScript、Vitest、OpenAPI 和 API 边界检查
- [ ] 自审秘密、正文日志、Trace 旁路、高基数 label、管理员越权、Markdown 外部资源、模型版本漂移、未跟踪文件和 migration 回滚
- [ ] 更新 evidence 与 Tasks 真实状态，明确未运行 Next.js build/Docker build 和未覆盖边界
- [ ] 用户人工验收后再根据当轮明确授权决定是否 commit、push
