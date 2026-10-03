# 质量诊断与提示词管理：首期并行交付

2026-10-03。用户批准既有 OpenSpec 首期范围，并直接授权按仓库截图与当前风格补齐设计状态。四条功能线使用独立 Git worktree，统一集成到 `codex/learn-quality-prompt-integration`；未推送、开 PR、迁移业务库、部署或覆盖主工作区。

## 功能与边界

**资料反馈**只绑定本人资料模式、成功且 `trace_complete=true` 的 LearningTurn。学习页入口仅传不可变 source/trace 身份；基础授权默认未勾选。本人可查看列表/详情、补充、批准或拒绝指定候选片段追加授权、撤销、未领取撤回与关闭。管理员有脱敏概览/队列、领取/转交、Trace/记录排名、逐字段正文读取、公开回复、内部备注、状态归因与无正文访问审计。工单与授权版本参与并发检查，角色判断先于对象查找。

正文使用可轮换 keyring 加密，来源、文件/chunk/当前处理版本与授权每次重新核验。撤销、到期、关闭立即拒绝管理员正文读取；客户端取消旧请求、清除旧正文且保留脱敏元数据，避免重复请求循环。现有每日文件调度任务接线保留清理；正文失效 7 天内物理清理，工单/Trace 90/180 天上限及账号删除匿名化按既有规则执行。

**提示词管理**只纳管实际 `question_generator/practice_generate` 与其公共片段。支持管理员列表、不可变版本时间线、草稿编辑、固定依赖、Diff、无模型合成预览、显式固定样例评测、完整指纹核验、原子发布、原因必填的回滚新版本、启停与无正文审计。草稿冲突保留输入和原发布基准，不能悄悄改成当前活动版本重发。

PracticeRun 与 AgentRun 在同一入队事务固定版本、依赖 hash、动态输出 Schema、模型参数及无正文来源引用；worker/provider 只使用入队快照。发布、退役、停用及 Settings 模型变化不改变旧任务，重试沿用同一快照。新受管生成无有效活动版本稳定返回 `PROMPT_RUNTIME_UNAVAILABLE`，不会残留半个入队事务。未纳管场景和历史业务结果仍使用既有执行/读取规则。

共享 `AdminRoute` 在挂载业务组件前拒绝非管理员；共享后台壳与角色导航由集成者独占。Prompt 草稿只保留在当前认证管理员后台范围的内存，身份替换、降权、退出或离开后台销毁；无浏览器持久存储或 URL 正文。

## 分支、worktree 与提交

工作目录共同前缀：`/Users/lilin/Documents/Codex/2026-10-03/task/worktrees/`。

| 分支 | worktree 目录 | 功能提交 |
| --- | --- | --- |
| `codex/learn-quality-backend` | `next-quality-backend` | `cc7fd93` 基础接口；`b6cedcb` 授权/清理回归；HEAD `209907a` 证据 |
| `codex/learn-prompt-backend` | `next-prompt-backend` | `24582ee` 基础领域；`ad542da` / `f481cfa` 运行/不可变约束；HEAD `f1473b1` 隔离测试 |
| `codex/learn-quality-ui` | `next-quality-ui` | `c0d78d6` API；`8836eaa` 本人页；`af401f0` 后台；`fb51789` 撤权缓存；`46a836b` 布局；HEAD `b52ff31` 未领取授权门禁 |
| `codex/learn-prompt-ui` | `next-prompt-ui` | `16c2cb5` API；HEAD `cea842b` 完整管理与草稿恢复 |
| `codex/learn-quality-prompt-integration` | `next-integration` | 四线已 cherry-pick；公共契约 `9a29c50`、迁移/真实运行 `459ea2c`、队列回归 `db4f798`、SDK/调度 `b05c95f`、共享壳 `88b5df8`、学习入口 `ae512cf` / `5e1dcca`、完整 UI `8d047ca` / `ac50cad` / `d475136`、缓存/门禁 `4d0d298` / `5b83973`；文档与最终格式收尾见本文所属提交 |

上一批三个可靠性 worktree 与独立集成 `a9aa5db` 保留。本批从该提交开始，因此新集成分支包含上一批修复；功能分支只负责各自文件，不交叉编辑主工作区。主工作区仍为 `main@57629ef`，保留用户原有 `.gitignore` 未提交改动。

## 已执行验证

| 验证 | 结果及实际边界 |
| --- | --- |
| 完整后端 pytest | **506 passed、41 skipped、1 warning**；含真实 PostgreSQL 的质量/Prompt/练习/资产与运行快照测试。跳过项为既有文档、学习数据库或外部真实模型的显式环境门禁；没有把 skip 算作通过。warning 为本地 Qdrant 模式 payload index 提示 |
| 质量专项 | 82 passed：64 单元/策略/清理/source + 18 PostgreSQL/HTTP，含跨用户、并发读与撤销锁、当前版本退休、授权范围、保留和匿名化 |
| Prompt 专项 | 28 passed：22 单元 + 6 PostgreSQL，含模板/注入边界、完整指纹、并发发布、不可变正文/依赖/评测集、回滚/启停 |
| 真实练习与调度 | 已入队任务跨发布/停用/模型变更仍用旧版本、新任务停用拒绝、重试同一 AgentRun 与取消状态通过；真实每日调度清理回归最终另复核 **1 passed** |
| Python 静态验证 | Ruff check 通过；Ruff format **181 files** 通过；mypy **113 source files** 通过。最后发现调度测试一处格式差异，已修正并复核 |
| 迁移 | 三个独立库均 `upgrade 07 → downgrade 04 → upgrade 07` 成功，单一迁移 head；最终 `alembic check` 无新增差异 |
| 实际 HTTP | 独立 Uvicorn、合成真实 JWT/AuthSession 与 subprocess curl **32 项通过**：401/403/404、角色优先、跨用户、幂等、无正文元数据、字段读取、撤权旧版本 409/当前失活 403、no-store 与新指纹未评测发布 409 |
| OpenAPI | 从实际应用再次导出，与已提交 OpenAPI 字节一致；SDK 由该文件生成，前端同步检查通过，无手写 DTO |
| 最终前端 | `pnpm check` 全部通过：格式、API 边界、type-aware Oxlint、Next typegen + TypeScript、**49 files / 252 Vitest tests**、OpenAPI 同步。新增测试涉及授权默认状态、角色隔离、字段缓存/到期、迟到请求、失败草稿、版本基准与历史恢复 |
| 构建 | 最终 `pnpm build` 成功，包含全部新路由；Python wheel/sdist 构建成功；Compose 语法/插值检查通过。未构建 Docker image、未启动镜像、未部署 |
| OpenSpec | 两个变更 `openspec validate … --strict` 实际执行通过；文档结构通过不替代功能测试 |

## 真实浏览器与设计证据

使用一处 Ego Lite task space（16），真实登录独立合成库的本人、另一学习账号与管理员，API 18013 / Next 18014。未绕过页面登录、未访问真实用户资料或真实 Prompt。截图在 [质量与提示词浏览器证据](../ui-design/evidence/quality-prompt-20261003/README.md)。

- 通用问答无反馈入口，资料回答有入口，授权初始 false；提交活动来源复用幂等工单；本人列表/详情/补充可用。另一个用户读取该 ID 被拒绝且没有原问题描述，普通账号后台功能不挂载。
- 管理员概览/队列无正文；进入详情仍无问题/回答，明确选择授权字段后才显示。领取、公开回复、内部备注已实际保存；本人只看到公开回复，未出现内部测试标记。
- 本人撤权后问题描述清除；管理员重新进入工单后无旧回答、无正文读取控件。完整资料 fixture 的指定候选追加授权由本人明确同意后才能读取；full、FTS-only 实际离线对照成功。本人关闭后状态 closed、补充 disabled、描述不可见。
- Prompt 已发布版本实际只读；创建 v3、保存、Diff、无模型预览可用；没有评测时发布按钮 disabled。回滚无原因 disabled，填原因后产生 v4，v2 退役、v4 成为新活动版本（同指纹的合成证据复用）；停用/重新启用真实成功。
- 链接离页有未保存确认。浏览器原生后退再前进后恢复内存输入，并显示恢复提示；显式放弃清除。普通账号访问实际 Prompt 路由被拒绝，无正文控件。
- 本人详情、Prompt 详情与正文区的 375×812 视口均 `document.scrollWidth == innerWidth == 375`；正文编辑区 343px，可垂直滚动。桌面列表/详情/预览/回放亦实际查看。localStorage 空；sessionStorage 只有 Ego 浏览器工具握手 ID，无 Prompt/诊断正文。

原始 Pen 的本批完整页面未能在本机找到，已经报告后获得用户“授权设计”。实际参考为仓库反馈 56–61 截图及 `06-admin-global-qa-complete.png` / 当前后台风格；不声称原 Pen 逐像素验收或用户人工验收已完成。共保存并查看 20 张截图。最后补充截图接口连续超时，未再反复请求；关闭与普通 Prompt 拒绝以实际页面状态读取完成，空间随后正常结束。最终小幅类别换行、Diff 中文和未领取门禁由专项回归/最终构建核验，不将未保存的截图计入证据。

## 运维前提、清理与剩余限制

- 本轮三个专属 PostgreSQL 测试库已 DROP，精确合成 auth Redis namespace 读回为空；仅结束本轮 18013/18014 进程和该浏览器空间。共享 PostgreSQL/Redis 与既有业务进程不启停。worktree 与分支保留供审查。
- 质量反馈启用前需要有效诊断 keyring；受管生成启用前需要真实管理员 CLI 初始化草稿、显式实际模型评测和发布。步骤见 [后端 README](../../backend/README.md)。本轮合成 provider 评测验证流程/输出契约，**未调用外部真实 Qwen**，不能当真实模型质量报告。
- 候选对照仅复用历史排序，FTS 不是 BM25；Hybrid-only/无 Rerank 同一融合记录，不提供独立模式延时、因果结论、解析/索引重跑或新生成答案。单个合成候选指标为 1 不是业务准确率结论。
- 另一浏览器撤销后，已打开管理员页面需要重新读取授权状态；本期没有跨浏览器推送契约。每次服务端敏感读取仍即时检查授权；当前页自然到期/本地撤权会清正文。
- 浏览器历史导航不能可靠取消；内存恢复限当前管理员后台会话。离开后台、退出或角色失效销毁草稿，整页刷新依靠 beforeunload 提示，不提供持久化恢复。
- 截图复核还记录两处非阻塞文案：拒绝访问时加载提示仍在；已撤销卡的原授权范围标题仍写“管理员可查看”。正文与读取控件已按权限隐藏，但这两处提示可在下一轮统一优化。
- 维护首期扫描/加锁尚无大规模性能证据。其他 source、Prompt 场景、简历/JD 上下文与尽力历史重跑留待后续已确认规格分期，不新建空角色或声称全量需求已完成。
- 本机本轮验证脚手架位于 task 的 `support/isolated_next_checks.py`、`next_http_smoke.py` 与浏览器合成 seed；其数据库名和环境护栏明确，不保存真实凭据。普通后端 `pytest` 会跳过未显式开启的数据库/真实模型分组。统一结果应查阅本表，不能仅比较默认测试计数。

## 后续真实模型评测

用户随后明确授权真实外部评测。原规则恶意输入过度拒答已补强，最终公共规则与练习生成各 4/4 通过，138 项相关后端回归通过。原始失败、一次上游失败及证据恢复过程均保留；详见 [真实模型评测记录](real-prompt-evaluation-20261003.md)。业务库、main 与部署仍未变更。
