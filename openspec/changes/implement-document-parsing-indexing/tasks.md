# Tasks：实现文档解析、索引与可验证检索

## 1. 规格与依赖

- [x] 更新 PRD 至 v0.8，固化解析、模型、图片、检索 Trace、反馈授权和管理员诊断边界
- [x] 完成 Proposal、Design、三份增量 Specification 与初始 evidence
- [x] 核对千问当前官方 Embedding/Rerank API、价格与限流，记录可漂移字段而不写入秘密
- [x] 更新 PRD 至 v0.11，确认 LangChain、LangGraph、LlamaIndex 的项目级真实使用要求与职责边界
- [x] 更新 PRD 至 v0.12，将向量存储决策由 pgvector 修订为 Qdrant，并补充权限过滤、双库发布、清理与恢复边界
- [x] 更新 PRD 至 v0.13，将首期范围修订为 PDF 页面级 OCR，继续排除 DOCX/Markdown 内嵌图片与通用视觉理解
- [x] 确认 PDF 原生文字提取与 OCR 前页面渲染统一使用 `pypdfium2`（PDFium），不在业务解析链路继续使用 `pypdf`
- [x] 完成 OCR 引擎与页面渲染选型，锁定语言包、版本、部署方式、默认页数/像素/时限、并发和质量阈值，并记录隐私、许可证、资源与降级边界
- [x] 通过包管理器增加 LlamaIndex、LangChain 千问兼容适配、DOCX、Markdown、Qdrant client、`pypdfium2`、OCR 识别和必要分块依赖，更新锁文件

## 2. 数据库与任务骨架

- [x] 创建解析、分块、通用任务、向量操作幂等记录所需的 Alembic 迁移；不得启用 `vector` 扩展
- [x] 实现 `BackgroundTask` 领取、短事务、租约续期、lease token、取消和重试分类
- [x] 实现 `DocumentProcessingVersion`、`DocumentChunk`、活动版本唯一约束，以及 Qdrant collection/profile/point 身份映射
- [ ] 实现 `RetrievalTrace`、阶段诊断事件、30 天默认保留和质量工单合法延长钩子
- [x] 实现显式 Qdrant 初始化/校验命令，创建 1024 维 Cosine collection、`user_id` tenant index 与高频 UUID payload index；应用启动不得隐式改 schema
- [ ] 验证干净隔离数据库 upgrade/downgrade/upgrade，以及 Qdrant 不可用、未初始化、鉴权失败和 schema 不兼容行为

## 3. 文档解析与分块

- [x] 实现项目解析结构到 LlamaIndex 节点的受控 transformation，稳定映射节点 ID、来源锚点和策略版本
- [x] 将现有 PDF 上传结构校验从 `pypdf` 迁移到 `pypdfium2` 或独立安全校验边界，以损坏、加密、嵌入附件、页数和资源限制回归测试证明门禁未降低后再移除 `pypdf`
- [x] 实现 PDF 逐页文字层提取、待 OCR 页面判定、页面级 OCR、原页序合并、来源/质量标记、图片计数和噪声边界
- [x] 实现 OCR 页数/像素/DPI/并发/时限门禁、中间文件清理，以及空结果、低质量、资源超限和短暂运行时失败分类
- [x] 实现 DOCX 标题、段落、列表、表格、图片计数与不支持结构边界
- [x] 实现 TXT 段落解析与 Markdown AST、代码块、表格、alt 文本和外部图片禁止抓取
- [x] 实现结构感知分块、稳定来源锚点、内容摘要和策略版本
- [ ] 增加四类解析器、纯扫描 PDF、混合 PDF、重复文本防护、OCR 中间数据清理、确定性失败和资源限制测试

## 4. Embedding、索引与版本发布

- [x] 实现确定性测试 Embedding provider，以及经 LangChain 模型适配的千问 `qwen3.7-text-embedding` provider
- [x] 实现 AI 处理确认记录、后端发送前门禁和前端一次性确认交互
- [x] 实现 1024 维批量 Embedding、并发/超时/限流、脱敏日志和错误分类
- [x] 实现草稿解析版本、Qdrant `wait=true` 幂等 upsert/计数校验、PostgreSQL 活动版本原子发布与旧租约拒绝提交
- [x] 实现首次解析、重新解析、失败保留旧版、取消清理草稿和策略升级边界
- [ ] 实现同用户跨知识库复用、移动不重建、删除后立即退出检索、Qdrant 异步清理与周期对账

## 5. 混合检索与 Rerank

- [x] 实现 PostgreSQL 全文检索和 Qdrant Cosine 向量召回
- [x] 实现 PostgreSQL 授权范围解析、Qdrant payload 前置过滤、返回前 PostgreSQL 复核，以及 LlamaIndex Retriever 组合层的版本化融合与去重
- [x] 实现确定性测试 Rerank provider 和千问 `qwen3-rerank` provider
- [x] 实现基础混合排序与 Rerank 后排序分开记录，Rerank 必需策略失败时不静默降级
- [x] 实现各阶段候选 ID/排名/分数、策略版本、耗时和错误的脱敏 Trace，禁止记录 Query/片段正文或高基数 Prometheus label
- [x] 实现受保护检索 API、`trace_id`、稳定响应模型、分页/Top-N 边界和 RFC 9457 错误

## 6. 前端联调

- [x] 导出 OpenAPI 并重新生成只读前端 client
- [x] 在 file-management feature API、query/mutation options 中接入任务查询、取消、重试、重新解析和检索契约
- [x] 更新内容库文件状态、真实阶段、OCR 页数、分块计数、图片未识别提示和安全失败原因
- [ ] 增加前端 API、Query、状态组件和交互测试；不新增问答或向量调试页面

## 7. 自动化与真实验证

- [ ] 建立不含用户原件的四类合成固定夹具和检索 golden set；PDF 夹具同时覆盖原生文字层、纯扫描和混合页面
- [ ] 验证 `Recall@5 ≥ 90%`、来源定位完整率 100%、越权结果为 0，并分别报告混合与 Rerank 后指标
- [ ] 执行 FTS-only、Vector-only、Hybrid-only、无 Rerank 和完整策略消融，报告 Recall@K、MRR、nDCG、无答案判断、P95 延迟和错误率
- [x] 保持 PostgreSQL 全文检索为首期关键词基线；Qdrant BM25/sparse/hybrid 的中文 tokenizer 与租户 IDF 另立 OpenSpec 后再评估
- [ ] 使用隔离 PostgreSQL、隔离 Qdrant 和确定性 provider 验证取消、重试、并发 worker、租约过期、原子切换、移动、删除、孤儿点与缺失点修复矩阵
- [ ] 增加架构边界测试，证明 LangChain 与 LlamaIndex 进入真实链路且不会接管领域持久化、绕过 PostgreSQL 授权范围/Qdrant payload filter 或扫描非授权目录
- [ ] 使用真实 PostgreSQL/Qdrant/RustFS/千问及用户指定 PDF、DOCX、Markdown 和生成 TXT 执行脱敏 smoke
- [ ] 验证 Qdrant 锁版本单节点持久化、重启、collection snapshot 恢复、alias 清单恢复和 PostgreSQL 活动版本对账；不冒充生产高可用
- [ ] 真实后端 curl 门禁通过后执行前端隔离 Playwright E2E，并清理临时数据、任务、向量和测试服务

## 8. 自审与交付

- [x] 运行 Ruff、mypy、pytest、Oxfmt、Oxlint、TypeScript、Vitest、OpenAPI 和 API 边界检查
- [x] 自审秘密、正文/OCR 页面日志、OCR 中间文件残留、Trace 旁路、高基数 label、管理员越权、Markdown 外部资源、模型版本漂移、未跟踪文件和 migration 回滚
- [x] 更新 evidence 与 Tasks 真实状态，明确未运行 Next.js build/Docker build 和未覆盖边界
- [ ] 用户人工验收后再根据当轮明确授权决定是否 commit、push

## 2026-10-02 交付边界

已完成源码实现和基本隔离验证；本变更仍未达到全部 PRD 上线门禁，保持未归档。

- [x] OCR 固定采用用户指定 `qwen3.5-ocr`，真实合成图片识别成功，输出置信度保持 null
- [x] 真实千问合成文件上传 → 原生提取/扫描页 OCR → Embedding → Qdrant → 混合召回 → Rerank → 证据与 Trace 通过，覆盖四种文件格式及三种 PDF 模式
- [x] 隔离迁移 upgrade/downgrade/upgrade 通过；2026-10-02 获授权后业务库已迁移至 20261002_02
- [x] 七项真实 PostgreSQL/Qdrant 集成场景通过，含并发、缺失与多余点修复；仅测试隔离资源
- [x] 浏览器注册、AI 说明默认未选/按钮禁用、确认、TXT 上传和完成状态核验；截图接口超时，重新解析点击被遮挡，未记为通过
- [ ] 固定中文/同义/无答案 golden set、Recall@5/MRR/nDCG 与消融性能报告
- [ ] 无 PostgreSQL 版本记录的未知孤儿点扫描、完整故障矩阵及恢复后对账
- [ ] Qdrant 持久化重启、snapshot/alias 恢复演练
- [ ] 外部用户原件 smoke、供应商数据地域/留存条款确认与人工验收

保留独立 pypdf 上传安全校验门禁，PDFium 只负责业务提取和渲染。未勾选的复合任务存在未覆盖子项，不表示完全未实现。生成式问答由 implement-learning-quick-answer 独立交付；仍无管理员正文查看入口。

- [x] 修正公式/箭头/弯引号被 ASCII 白名单误判的 OCR 质量门禁，加入先红后绿回归及噪声拒绝测试；真实失败页重放通过，更新已部署 document-worker
- [ ] 用户重新解析该 PDF 后完成全文件索引验收（本次未自动修改用户任务）

### 后续评测证据

- [x] 8 份合成 TXT、16 个中文精确/同义问题的 FTS/Vector/Hybrid/No-Rerank/Full 离线候选重放，来源定位完整；详见 `../implement-learning-quick-answer/retrieval-evaluation.md`。
- [ ] 四格式完整 golden set 和独立消融性能实验；检索层无答案正确率仍为 0，不把生成层三个拒答样例冒充检索门禁达标。
