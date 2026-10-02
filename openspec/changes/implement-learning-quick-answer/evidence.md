# 学习快速回答实现与验证证据

日期：2026-10-02。本机源码开发环境，尚待用户人工验收。

## 实现与自审

模型按用户指定为 `qwen3.8-flash`，非思考、temperature=0、严格 JSON Schema；默认中文，可选英文。Prompt 公共/角色/场景不可变组合、版本与摘要保存在轮次运行元数据中，场景版本 3。用户历史仅最近六个问题用于指代，资料模式每次重新检索，旧答案不作为证据。引用编号和正文标记由后端核验，拒答规范化；英文长回答出现在中文模式时明确失败并允许重试。

私有会话支持固定范围、分页、标题、重命名、软删除、反馈。同会话锁、处理轮次唯一约束与租约限制并发；模型调用在事务外；同 request_key 成功复用、失败重试，问题/语言冲突拒绝。生成完成重新核验来源权限、活动版本和会话删除状态；历史失效引用隐藏正文与文件名。独立问答 consent 不复用旧文档授权。接口不公开 Prompt、模型密钥或未授权正文；生成外部 LangSmith 自动追踪关闭。前端遵循 feature API/Query/shared ApiError/生成 SDK。

自审发现并修复 ORM 错误传入回答语言，以及默认中文的真实模型回归；修复后重新完成以下验证。

## 自动化验证

- Ruff check、Ruff format check 通过；mypy 66 个源码文件通过。
- 后端全量 pytest：133 passed / 15 skipped。跳过项是显式隔离或真实供应商测试，不能视作通过。
- 独立 `run_learning_checks.py --real-models --quality`：16 passed，含迁移 upgrade/downgrade/upgrade、真实 PostgreSQL/Qdrant 权限与生命周期、真实千问通用/资料中文回答、检索质量和三个无答案拒答。隔离 DB 已 DROP，collection 清理。
- 旧代码隔离回归遇到 ORM 构造失败后被停止，finally 已清理；不把该运行记为通过。
- 前端 pnpm check 全部通过：Oxfmt、API 边界、Oxlint、TypeScript、Vitest 59 tests / 17 files、生成客户端同步检查。后端重新导出 OpenAPI 字节比对一致。测试 dev 自动添加的 tsconfig include 已恢复。
- OpenSpec 两个变更 strict validate 与 git diff --check 通过。
- 合成检索详见 retrieval-evaluation.md：8 TXT、16 精确/同义问题，Full Recall/MRR/nDCG=1，来源完整率 100%，错误率 0。FTS 是 PostgreSQL ts_rank_cd，非 BM25。离线候选重放和阶段耗时不代表独立消融性能或因果贡献。
- 检索层三个无答案正确率仍为 0；生成层三个拒答均通过。四格式完整 golden set、生产分布和独立压测尚未覆盖。

## 业务库与本机运行

用户明确授权后端开发直接迁移业务库，根 AGENTS.md 已记录目标核验、可恢复备份与迁移后读回要求。业务库 xuemian_ai 从 20261002_01 升级至 20261002_02，再次读回为 head。备份在 `.runtime/backups/`，0600，122283 bytes，pg_restore --list 通过；sha256=a4d079b3185af2bb88012f3f4cbd25ad115837649da830c2b25abf6b7330197c。不提交或展示备份内容。

本机 API 已优雅重载为最终代码，/api/v1/health/live 与 ready 均 200；OpenAPI 有学习路由；未认证 /api/v1/learning/conversations 为 401；前端 /learning 为 200。这些检查只证明运行与访问边界，不能代替业务验收。未操作外部 PostgreSQL/Redis 生命周期。

## 浏览器与验收边界

隔离合成账号验证首次 AI 说明默认未选/确认禁用、主动确认、真实资料回答及 PDF/TXT 引用预览、反馈刷新持久化、重命名刷新持久化和确认删除后历史移除。截图接口超时，无截图视觉证据。最新语言版本另经浏览器验证：英文问题在默认中文模式得到中文通用回答；“用一个例子解释它”延续事务隔离主题；合成资料中的月球基地年份问题明确拒答；选择 English 后得到英文资料回答及 PDF/TXT 引用。输入框在视口外时 Ego 自动滚动失败，经定位并滚动后完成交互，不把该工具失败记为业务失败。

未自动重试用户此前失败 PDF；全文件验收、未知孤儿点完整故障矩阵、Qdrant 恢复演练、供应商地域/留存条款、用户人工验收仍待完成。完整 Prompt 管理台、质量工单、笔记与出题不在本次实现。未运行 Next.js build / Docker image build；未 commit/push/PR。

隔离浏览器驱动已正常结束，临时 DB 已 DROP，存储/Redis/Qdrant 资源清理；Ego space 7 本轮标签已关闭。保留业务后端、前端与原有 worker 运行。

## 后续 Pen 设计核查

2026-10-02用户要求严格对照设计稿后，实际读取Pen06/07截图与图层，核对页面DOM尺寸及源码。发现当前实现未严格还原满高侧栏、学习三模式、对话气泡和输入区，设计验收不通过；前述功能/测试结果不代表视觉还原合格。详见 `../../../docs/ui-design/implementation-audit-2026-10-02.md`。本次没有修改功能源码或设计稿。
