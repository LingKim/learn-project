# Evidence：文档解析、索引与可验证检索

## 当前状态

- 状态：需求共识与 OpenSpec 已完成，尚未开始实现。
- Git：本轮未经授权，不 commit、不 push。
- 模型调用：尚未调用千问，未产生模型费用。
- 数据库：尚未执行迁移，未启用项目数据库的 `vector` 扩展。

## 已核对事实

- PostgreSQL 版本为 18.1；宿主可用 `pgvector 0.8.2`，当前项目数据库 `installed_version=none`。
- 当前 `FileCleanupTask` 有持久化领取、租约和 `FOR UPDATE SKIP LOCKED`，但语义、长事务、无续租和无阶段进度使其不适合直接承载解析。
- PDF 已有 `pypdf`；DOCX 当前只有校验级 ZIP/XML 读取；Markdown 当前按纯文本校验；尚无 pgvector adapter、正式分块器或 Embedding provider。
- `.env` 中 `DASHSCOPE_API_KEY` 已确认非空；检查未输出或保存其值。

## 千问官方页面核对

以下为 2026-08-30 页面快照中的可漂移事实，不作为永久价格或限流承诺：

- `qwen3.7-text-embedding`：支持 256、512、768、1024（默认）、1536、2048、2560 维；批次上限 20，每批最多 128,000 Token；模型页当时显示文本输入 ¥0.5/M Token、RPM 24K、TPM 1M。
- `qwen3-rerank`：官方定位为文本检索与 RAG；最多 500 个候选文档，单条最多 4,000 Token；模型页当时显示文本输入 ¥0.5/M Token、RPM 5K、上下文 30K。
- `qwen3-vl-rerank`：官方定位为图片和视频参与的多模态重排；本阶段只有文本解析结果，因此明确不选用。
- pgvector 官方 HNSW 文档说明 `vector` 索引最多支持 2,000 维；选择 1024 维同时满足模型默认平衡档位与 HNSW 约束。

## 真实 smoke 输入

这些文件位于仓库外，只用于用户明确授权的真实 smoke，不复制到仓库、不提交 Git：

- `/Users/lilin/Desktop/20260608 黄佳直播回放分享版.pdf`：6,511,794 bytes，41 页；38 页可提取文字，3 页无可提取文字，41 页检测到图片。
- `/Users/lilin/Desktop/JDT_产品库_需求规格说明书_V1.0.docx`：120,934 bytes，检测到 9 个内嵌媒体文件。
- `/Users/lilin/Desktop/java/java 高级/r-blog-doc/chapter15/doc/15.1 AI 核心组件设计｜AI Agent 组件解析与技术选型.md`：149,364 bytes，标题层级丰富，未发现真实 Key/密码或图片引用。
- TXT：实施时生成不含敏感信息的固定中文夹具。

## 验证边界

- 以上文件存在、格式和静态结构已只读核对，不等于解析、Embedding、索引或检索已经通过。
- 真实模型 smoke 必须只记录状态、耗时、批量、模型 ID 和质量指标，不记录正文、向量、Key 或完整服务响应。
- 当前没有 OpenSpec CLI 可执行证据；若实施环境仍不存在，需明确报告而不能用目录结构检查冒充 strict validate。
- 按项目规则不运行 Next.js build 或 Docker image build，除非用户另行明确要求。

## 2026-08-30 RAG 可诊断性补充

- 用户明确要求补齐“我要反馈”与管理员链路排查平台；当前变更只吸收其底层依赖：`RetrievalTrace`、策略版本、阶段候选与排名、消融评测和隔离回放边界。
- 普通 Trace 不保存 Query 或片段正文，管理员不能仅凭 `trace_id` 读取用户内容；用户授权工单与管理员诊断台由独立 `implement-ai-quality-feedback-console` 变更定义。
- 微信文章《RAG 跑通之后，我才发现真正缺的是一个“运维平台”》用于发现治理问题，不作为产品能力已验证证据；文中的固定门禁数值、60+ 字段、自研引擎必要性、成本归因和 MCP 宣传口径未直接照搬。
