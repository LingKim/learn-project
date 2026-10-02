# Evidence：文档解析、索引与可验证检索

## 当前状态

- 状态：PDF 页面级 OCR 的产品范围与 OpenSpec 行为已修订，OCR 引擎和资源参数仍待选型，尚未开始实现。
- Git：本轮未经授权，不 commit、不 push。
- 模型调用：尚未调用千问，未产生模型费用。
- 数据库：尚未执行解析索引迁移；项目已决定不启用 PostgreSQL `vector` 扩展，Qdrant 尚未部署或接线。
- AI 框架决策：已确认 LangChain、LangGraph、LlamaIndex 的项目级职责；LlamaIndex 与 LangChain 在本变更中的真实接线尚未实现或验证。
- OCR 决策：2026-09-01 已确认首期增加 PDF 页面级 OCR，继续排除 DOCX/Markdown 内嵌图片和通用视觉理解；PDF 原生文字提取与 OCR 前页面渲染选用 `pypdfium2`（PDFium），OCR 引擎与资源阈值仍待选型。本轮未安装依赖或执行识别。

## 已核对事实

- PostgreSQL 版本为 18.1；宿主虽可用 `pgvector 0.8.2`，当前项目数据库 `installed_version=none`，并已由产品决策改为不启用。
- 当前 `FileCleanupTask` 有持久化领取、租约和 `FOR UPDATE SKIP LOCKED`，但语义、长事务、无续租和无阶段进度使其不适合直接承载解析。
- 当前后端依赖和上传校验仍使用 `pypdf`，尚未安装或验证 `pypdfium2`；DOCX 当前只有校验级 ZIP/XML 读取；Markdown 当前按纯文本校验；尚无 Qdrant client/adapter、正式分块器或 Embedding provider。
- 当前依赖已包含 LangChain、LangGraph，尚未包含 LlamaIndex；本次只更新需求与 OpenSpec，未安装依赖或修改锁文件。
- `.env` 中 `DASHSCOPE_API_KEY` 已确认非空；检查未输出或保存其值。

## 千问官方页面核对

以下为 2026-08-30 页面快照中的可漂移事实，不作为永久价格或限流承诺：

- `qwen3.7-text-embedding`：支持 256、512、768、1024（默认）、1536、2048、2560 维；批次上限 20，每批最多 128,000 Token；模型页当时显示文本输入 ¥0.5/M Token、RPM 24K、TPM 1M。
- `qwen3-rerank`：官方定位为文本检索与 RAG；最多 500 个候选文档，单条最多 4,000 Token；模型页当时显示文本输入 ¥0.5/M Token、RPM 5K、上下文 30K。
- `qwen3-vl-rerank`：官方定位为图片和视频参与的多模态重排；本阶段只有文本解析结果，因此明确不选用。
- 1024 维继续采用千问模型默认平衡档位；Qdrant collection 必须显式配置 1024 维与 Cosine，模型或维度不兼容时使用独立索引 profile，不在同一 collection 中混写。

## 真实 smoke 输入

这些文件位于仓库外，只用于用户明确授权的真实 smoke，不复制到仓库、不提交 Git：

- `/Users/lilin/Desktop/20260608 黄佳直播回放分享版.pdf`：6,511,794 bytes，41 页；38 页可提取文字，3 页无可提取文字，41 页检测到图片。
- `/Users/lilin/Desktop/JDT_产品库_需求规格说明书_V1.0.docx`：120,934 bytes，检测到 9 个内嵌媒体文件。
- `/Users/lilin/Desktop/java/java 高级/r-blog-doc/chapter15/doc/15.1 AI 核心组件设计｜AI Agent 组件解析与技术选型.md`：149,364 bytes，标题层级丰富，未发现真实 Key/密码或图片引用。
- TXT：实施时生成不含敏感信息的固定中文夹具。

## 验证边界

- AI 三框架职责已写入 PRD、架构基线和本 OpenSpec，但“文档已更新”不等于 LlamaIndex 已接线或三者已有生产运行证据。
- 以上文件存在、格式和静态结构已只读核对，不等于解析、Embedding、索引或检索已经通过。
- 真实模型 smoke 必须只记录状态、耗时、批量、模型 ID 和质量指标，不记录正文、向量、Key 或完整服务响应。
- 当前没有 OpenSpec CLI 可执行证据；若实施环境仍不存在，需明确报告而不能用目录结构检查冒充 strict validate。
- 按项目规则不运行 Next.js build 或 Docker image build，除非用户另行明确要求。

## 2026-08-30 Qdrant 决策修订

- 用户要求将向量数据库从规划中的 pgvector 改为 Qdrant；当前尚未开始解析/索引实现，因此没有生产向量数据迁移或停机切换。
- 本轮只修订 PRD、架构边界和 OpenSpec，并记录官方资料调研；尚未增加 Qdrant 依赖、Compose 服务、环境变量、collection、payload index、业务代码或测试。
- PostgreSQL 继续保存正文、分块来源、权限、活动版本、全文检索和 Trace。Qdrant point 不保存正文，必须先按 PostgreSQL 当前授权范围生成 payload filter，命中后再回 PostgreSQL 复核并加载正文。
- 双库发布采用“Qdrant 隔离写入并校验 → PostgreSQL 原子切换活动版本”；撤销采用“PostgreSQL 立即撤权 → 持久化任务异步删除 Qdrant 点 → 周期对账”，不宣称跨库 ACID。
- 官方能力与约束已整理到 `docs/architecture/qdrant-vector-store-research.md`，覆盖 collection、多租户 payload/tenant index、过滤、`wait=true` 幂等写删、alias 原子边界、一致性、副本、snapshot、异步客户端、版本锁定和 BM25/sparse/hybrid；该调研不是运行或性能验证。
- Qdrant 虽支持原生 BM25 与 dense+sparse 混合查询，但中文 tokenizer、多租户 IDF corpus 和融合质量尚未在本项目验证，因此本变更继续使用 PostgreSQL 全文检索，不扩大为关键词引擎迁移。

## 2026-08-30 RAG 可诊断性补充

- 用户明确要求补齐“我要反馈”与管理员链路排查平台；当前变更只吸收其底层依赖：`RetrievalTrace`、策略版本、阶段候选与排名、消融评测和隔离回放边界。
- 普通 Trace 不保存 Query 或片段正文，管理员不能仅凭 `trace_id` 读取用户内容；用户授权工单与管理员诊断台由独立 `implement-ai-quality-feedback-console` 变更定义。
- 微信文章《RAG 跑通之后，我才发现真正缺的是一个“运维平台”》用于发现治理问题，不作为产品能力已验证证据；文中的固定门禁数值、60+ 字段、自研引擎必要性、成本归因和 MCP 宣传口径未直接照搬。


## 2026-10-02 实现与当前验证记录

本节是当前事实，前文 2026-08/09 记录保留为历史。实现未提交，OpenSpec 未归档，生产上线门禁尚未全部完成。

### 模型及官方契约

用户指定千问 `qwen3.5-ocr`。实际读取千问 OCR/视觉文档与模型页，使用 user-only OpenAI 兼容请求、内存 Base64 PNG、最大输出 16384，finish_reason 必须 stop。没有数值置信度时保存 null；不让模型自评代替供应商信号。RapidOCR 与连带依赖已移除。Embedding 通过 LangChain OpenAIEmbeddings，明确为同步与异步 HTTP client 注入 trust_env=False；不修改本机全局代理。

- OCR 模型页：https://www.qianwenai.com/models/qwen3.5-ocr
- OCR 文档：https://platform.qianwenai.com/docs/developer-guides/multimodal/ocr
- 视觉文档：https://platform.qianwenai.com/docs/developer-guides/multimodal/vision
- 重排模型：https://www.qianwenai.com/models/qwen3-rerank
- 合成图片真实 OCR 通过（约 3430 ms，confidence_available=False）；Embedding 返回两个 1024 维向量，重排正确优先数据库证据。没有发送用户原件，没有记录密钥/正文/向量。

### 已实现链路

新增版本化文档处理、ProcessingAttempt、AI 确认、通用任务、来源正文块、索引 profile、向量清理操作和脱敏 Trace。上传校验后自动排队；本人确认 AI 说明后领取；事务外提取/OCR/Embedding/Qdrant；lease token 与 generation 拒绝旧任务发布；新版本全量写入并计数核验后原子发布，失败保留旧活动版。首次 profile 使用 PostgreSQL upsert，避免并发唯一冲突。清理领取先提交，外部删除事务外执行，幂等到期重试。

Qdrant 锁定服务/client 1.15.1，1024 维 dense/Cosine，无正文 payload。显式 CLI 初始化 tenant/UUID 索引，运行时仅校验。按 PostgreSQL 授权版本前置过滤，候选融合前和返回前再次复核。关键词使用 jieba + PostgreSQL FTS，融合使用真实 LlamaIndex QueryFusionRetriever RRF，不调用生成模型。

每 worker 每 60 秒逐版本对账：精确比较活动版本 chunk ID，删除多余点、缺失时创建重新解析任务；退休/失败/取消版本重复删除以处理旧 worker 延迟写入。完全缺失 PostgreSQL 版本记录的未知点扫描尚未实现；不要将本机制称为全部孤儿矩阵已通过。

前端沿统一 feature API、Query/Mutation、共享解包和生成 client 接入确认、轮询、取消、重试及重新解析；只显示真实阶段/计数，不新增问答或调试页面。Markdown 段落定位使用结构块序号；超长表格按行与内容分段重复表头，表头自身超限拒绝处理。

### 自动与真实验证

- 前端 pnpm check：Oxfmt、Oxlint/API 边界、TypeScript、15 个文件共 51 项 Vitest、生成 client 检查通过。
- 后端 Ruff 与 mypy（59 个源码文件）通过；全量 pytest 最终数量见下文追加记录，独立隔离测试默认跳过。
- scripts/run_document_integration.py：七项真实 PostgreSQL/Qdrant 测试通过；迁移 upgrade → downgrade 20260830_01 → upgrade 通过。覆盖处理/检索/Trace/隔离、确认门禁/排队取消、重新解析失败保留旧版、过期 lease 拒绝发布、移动删除撤权/清理、额外点删除与缺失重建、并发 worker 共用 profile。
- scripts/run_document_smoke.py：真实 API + RustFS 上传 + 两个独立 worker + PostgreSQL/Qdrant，TXT/MD/DOCX/原生 PDF 合成文件全部索引并检索，未认证 401/跨用户 404/Trace 通过。确定性 provider 只验证接线。
- scripts/run_document_smoke.py --real-models：真实千问四格式及原生/扫描/混合 PDF 共六份合成资料，OCR/Embedding/索引/检索/Rerank/Trace 全链路通过。不是中文生产质量评测，未宣称 Recall@5 目标通过。
- ego 浏览器空间 6：合成账号注册，AI 说明默认未选、确认按钮 disabled，确认后 TXT 上传，最终已完成且已索引 1 个片段。Page.captureScreenshot 超时；重新解析按钮点击被 section 遮挡，未记为浏览器通过。空间已 finish，不修改用户原标签页。
- Compose config 与 git diff --check 通过；不等于镜像能构建或生产服务已启动。

### 清理与未验证项

唯一临时 DB、RustFS bucket、Qdrant collection 和测试 API/worker/Next dev 已清理，业务库未执行新增迁移；现有 PostgreSQL/Redis 生命周期未改变。模型 smoke 只发送合成资料，无用户原件。

未完成：固定中文/同义/无答案 golden set 与消融指标、Qdrant snapshot/alias/持久化重启演练、未知孤儿点扫描及完整故障矩阵、外部原件、供应商数据地域/留存条款确认、人工验收。未运行 Next.js build/Docker image build；未 commit/push/提交 PR。

### 最终复核补充

- 后端最终全量：110 passed / 7 skipped；7 个跳过场景已通过专用唯一隔离库脚本再次实际执行（7 passed）。本地 Qdrant 单元测试产生 payload 索引不支持警告，真实服务集成已校验索引。
- OpenSpec CLI 已可用，修正三份增量规格的 ADDED Requirements 及 ASCII Requirement/Scenario 标题后，`openspec validate implement-document-parsing-indexing --strict` 实际通过。这不表示全部任务或上线门禁已完成。
- 后端重新导出 OpenAPI 到临时路径后与仓库逐字节一致；前端完整 pnpm check 最终通过。
- Redis smoke 唯一前缀残留已只删除本轮四个精确前缀，并补入后续 smoke 清理流程；不操作业务 Redis 前缀。


## 2026-10-02 业务库与本机部署

用户当轮明确要求“抓紧部署”。已执行以下动作，本节覆盖前文“业务库未迁移”的历史状态：

- 只读核对 `.env` 目标：database=xuemian_ai、role=xuemian_ai_app，原版本 20260830_01；PostgreSQL/Redis/RustFS 已运行。未启停外部 PostgreSQL/Redis。
- 部署前 pg_dump custom 备份成功，86599 bytes，保存到 Git 忽略目录 `.runtime/backups/xuemian_ai-before-document-processing-20261002.dump`，权限 0600。该文件含业务数据，不提交/不展示内容。
- `alembic upgrade head` 实际完成，读回业务库版本 20261002_01，新增处理表已存在。
- `docker compose up -d --no-deps --no-build qdrant` 实际启动正式 Qdrant，使用 `xuemian-ai_qdrant-data` 持久卷。显式初始化正式 `xuemian_qwen_text_1024_v1`，schema 实际核验 green、dense 1024/Cosine、user_id/file_asset_id/processing_version_id payload 索引。
- API8000、frontend3000、file-worker、file-scheduler、document-worker 本机源码进程实际启动，PID/命令/cwd/日志清单位于 `.runtime/processes.json`。Next dev，无 Next.js build 或 Docker image build。Docker 中是基础设施，本机进程是开发部署，机器重启后需重新启动。
- 实际 health/live=200；health/ready=200（PostgreSQL/Redis/RustFS 全 up）；最新 OpenAPI 含 AI 确认及检索路由；未认证确认接口=401；前端3000 HTTP=200；五个受管进程仍存活。
- worker 已为既有有效资料补齐首次任务，聚合读回 pending=1；没有替用户记录 AI 同意，没有自动将未确认资料发送给模型。登录内容库后需本人确认说明。

本次部署未另行上传用户原件或在业务库创建测试账号；业务库上的真实文件 OCR/检索需用户登录确认并人工验收。上一节合成全链路、质量评测与恢复边界不变。未经授权未 commit/push。


## 2026-10-02 OCR 数学符号误判修复

- 用户反馈 PDF 在 OCR 阶段失败。只读任务进度为完成 1/2 个待 OCR 页；本地文字层统计确认实际待 OCR 页是第 2/4 页。
- 初次外部重放被自动审批拒绝；用户当轮明确回答“允许重放相关页面”后才发送相关页给千问，未保存或打印正文/页面图。
- 真实第 4 页复现：123 个非空白字符，Sm=28、Pi/Pf 各 1，无 U+FFFD，confidence=null；旧有效字符比例 0.7561，确切触发 DOCUMENT_OCR_LOW_CONFIDENCE。原因是固定标点白名单误将正常数学符号/弯引号算作噪声，不是已证明 PDF 不清晰。
- 最小回归 fixture 复用相同字符类别模式，旧 complete_ocr 测试实际失败，修正 Unicode M/P/S 分类后通过；新增纯符号、替换字符、控制/私用字符拒绝测试。保留有效比例 0.8，不关闭质量门禁。
- 修复后再次真实重放第 4 页：116 个字符，旧比例仍是 0.7759，新检查 accepted。模型返回随调用略有变化，两次均能说明原白名单误判，未把随机模型输出当作固定测试夹具。
- 后端 Ruff/mypy 与 115 项 pytest 通过，7 项隔离数据库场景本轮未重跑；OpenSpec strict validate 和 diff check 通过，无 build。
- 没有处理中任务后，仅重启受管 document-worker 加载修复，当前 PID 9528；未直接改用户失败状态或创建重试任务。用户可点击重试解析。前端文案改为质量检查未通过，不再断言需更清晰原件。
- 本次真实页重放只验证 OCR 质量判断已修复，完整 PDF 的再索引需重新解析后验证。未 commit/push。

- 前端新增“不把质量拒绝归因于原件不清晰”测试，状态组件 5 项通过，Oxlint/API 边界检查通过。
