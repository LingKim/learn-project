# Evidence：难点资产与文字知识精讲

2026-10-03。用户回复“开始开发”明确批准本期方案后实施；代码、迁移、本机运行和主要浏览器闭环已完成，用户人工验收待完成。开发验收阶段未执行 build、commit、push 或 PR。原有无关 `.gitignore` 修改保留。

## 实现与自审

- 后端新增私有难点、证据、追加事件、评分/提交/完成/删除 outbox、不可变文字卡片、持久化知识任务及复习结论。识别只消费上线后 grade_published，不自动历史回填。
- 策略使用 30 天、3 道不同中等/困难单知识点错误或部分正确、跨 2 次 attempt、最近两道仍错；主观 confidence < 0.7 不自动归因，多知识点只待确认。手动目标不伪造评分证据。
- 关联再练配置/题目均冻结目标；验证使用全部相关单知识点题的分母，未答/未评分/低置信题不能剔除。仅关联练习的新有效错误可回退掌握状态，并按回答时间与最后用户操作时间防迟到覆盖。普通练习评分不因目标版本变化失败。
- 用户/资料 owner 复合约束、私有权限、来源 revision/处理版本、lease/cancel/timeout、发布再校验已实现；失效来源保留卡片/事件但隐藏原文。GET 不写业务或调用模型。
- 前端经真实生成 SDK、feature API、queryOptions/mutationOptions 和共享 ApiError 接入；导航、profile、学习室、练习预填和报告集成。独立精讲不隐式创建难点。恢复存储只含 owner/target 隔离 UUID，不保存正文。
- 主 agent 自审和独立只读审查已执行。二次发现的改名后删除复活、正式难点精讲 409、旧 URL 遮盖新任务均修复；第三次发现的新旧主题证据互相 supersede 已按最终资产 identity 合并再投影，恢复当前权威有效证据并保留删除/忽略阻断，新增实库组合回归。最终独立源码复核未发现新阻塞；源码审查不替代运行验收。

## 自动化实际结果

各组有重叠，不能相加为唯一业务场景数量。

| 检查 | 最终结果 | 边界 |
| --- | --- | --- |
| 后端全库 pytest | 336 passed / 80 skipped / 1 warning | 默认跳过真实模型和部分基础设施；local Qdrant payload index 警告，不代表真实索引效果 |
| 新鲜隔离迁移及资产/练习领域 HTTP | 114 passed / 10 skipped | 真 PostgreSQL；upgrade head → downgrade 03 → upgrade 04；最后自动 DROP 测试库 |
| 后端 Ruff / format / mypy | 全部通过，156 格式文件 / 90 source files | 静态检查 |
| 前端 pnpm check | 36 文件 / 146 tests；格式、Oxlint/API 边界、TypeScript、OpenAPI 全通过 | 组件、Query 和 transport 测试不能替代实际业务路径 |
| OpenAPI | 最终 FastAPI 再导出与 openapi/openapi.json 字节一致；SDK check 通过 | 无手写重复 DTO |
| OpenSpec / Git / Compose | strict validate、diff --check、compose config --quiet 通过 | 不代表 build/部署或业务验收 |

隔离测试覆盖门槛边界、最新未评分提交 supersede、重评/乱序、低置信/多主题、ignore/revoke/rename/delete、所有者/用户禁用/admin 业务正文拒绝、资料处理版本/删除/移动/撤权、旧卡片、显式来源 refresh、取消竞争/超时/迟到发布、失败保留/重试、并发与完整分母。六轮真实 submit/projection 并发及超时保护也已验证。受保护真实格式管线单列如下。

## 真实模型与资料质量

最终 generation Prompt v4、grounding audit v3；使用配置中的 qwen3.8-flash。资料模式逐字段审查全部五部分，包括示例标题/正文、练习问题/自查点，服务器映射原文 span；未支持/缺项/伪造编号/截断响应均拒绝发布，不靠补写正文。

最终真实运行 `test_learning_knowledge_formats_integration.py` 与 `test_learning_knowledge_provider.py`：16 passed / 208.88 秒，包含 6 格式、4 真实 provider/audit 案例及 6 mock 协议检查。不能写成 16 个真实模型场景都发布成功。

| 实际合成资料格式 | Schema/引用映射 | 依据门禁 | 逐份五部分复核 |
| --- | --- | --- | --- |
| TXT | 通过 | 接受 | 未发现额外保证 |
| Markdown | 通过 | 接受 | 未发现额外保证 |
| DOCX | 通过 | 拒绝 | confirm once 扩大成 exactly-once 保证，拦截 |
| 原生 PDF | 通过 | 接受 | 未发现额外保证 |
| 扫描 PDF | 通过 | 拒绝 | 新增记录状态不变和令牌验证建议，拦截 |
| 混合 PDF | 通过 | 拒绝 | token consumed 扩大成记录保持 confirmed，拦截 |

真实分母：6 份均经过实际 DocumentWorker、PostgreSQL/Qdrant、protected RetrievalService/完整 Trace、实际模型生成与 audit；3 接受、3 拒绝。OCR 使用真实 provider，embedding/rerank 使用 deterministic fixture。故意未支持状态保证的真实反例也被 audit 拒绝。逐份检查是 AI agent 语义复核，不是用户人工验收；同模型家族的审计不是形式证明，不能外推自然资料、长文档或其他主题的准确率。

DOCX 使用完整事实段落；此前碎片化九段仅召回四段，缺 pending 事实，本次不证明碎片化来源的完整召回。格式管线不模拟 HTTP 202 或调用学习资产发布事务，持久化发布/取消由领域/worker测试和浏览器另行核验。完整合成来源/候选/audit在本机被忽略的 `.runtime/evidence/learning-assets-models/`，详见该目录 semantic-review.md。

## 本机迁移、备份与运行

已核对 `.env` 目标为本机 `xuemian_ai` 与本项目 app role；迁移前版本 `20261003_03`、活动练习任务 0；完成 0600 可恢复备份并验证 pg_restore --list 后升级，读回 `20261003_04`。

备份 `.runtime/backups/xuemian_ai-before-20261003_04-20261003T071137Z.dump`，215948 字节，SHA256 `e3cf338bf452e8095ebbc597200183cef0372537fe6b5cdddd914334ea133b92`。

受管 API PID 33600、practice-worker PID 33601、最终 knowledge-worker PID 40586；均核对实际命令/module 与 backend cwd。知识 worker 在活动任务 0 时精确重启载入最终 audit/projection；随后本人直接精讲实际生成第 2 版，证明该入口实际处理任务。GET `/api/v1/health/ready` 返回 ready，PostgreSQL/Redis/RustFS up。原 frontend/file/document/scheduler 进程保留。没有启停或重建外部 PostgreSQL/Redis。

本任务临时库（含首次失败遗留库）已精确清理，namespace 只读查询无残留；业务库与备份保留。运行是本机源码开发进程，不能代表生产镜像部署。

## 本人浏览器闭环

使用 ego-browser 单一 TaskSpace 15，p1/p2；仅使用合成通用主题，不选择/外发用户原件。保留现有历史，不删除用户数据。

- 空库 → 手动创建“数据库事务原子性” → 真实五部分卡片 v1，无伪 grade → 针对性再练预填目标/主题/来源 → 真实 plan/3 题生成 → 保存/提交三题 → 完成 → 报告实际相关/提交/评分/正确全部 3，低置信 0，300/300。验证通过仍保持用户的待学习状态。
- 难点详情追加实际复习结论版本；手动标记已掌握后 profile 不再显示该活动项，恢复学习中后重新出现。最终保留“学习中”供验收。
- 学习室选择该正式难点，基础“用过但不熟”、深度“快速理解”，成功复用已有精讲并生成 v2；刷新可见真实生成阶段/取消入口，完成后配置正确。v1 仍保留原基础/深度；再次生成取消后 v2 保留。
- 独立“HTTP 幂等性（验收样例）”直接精讲 v1 成功；最终受管 worker 重启后 v2 成功，正式资产仍只有 1 个，没有隐式创建难点。
- 网络响应丢失刷新、低置信、来源失效、失败与重试等反例由自动化覆盖；浏览器没有逐一制造这些反例，也没有冒称全部浏览器异常矩阵通过。

保留样例 ID：难点 `9ec7f5e7-760b-49f9-b5b8-18897c234737`；绑定精讲 `3589566c-8acd-4742-9ae3-8769e3a724bc`；直接精讲 `f366f2a8-b926-42e8-b1e9-53e4d29e6789`；题集 `3caea897-d03a-4d6c-9542-5a724eb97c37`，attempt `98b7b8a5-8f6f-4ddd-8b87-a559019feccb`。样例是本次验收新增合成内容，保留给用户复核。

## Pen 与视觉核验

原稿和校准稿均由 Pen MCP 读取/导出，不直接 cat 加密 .pen。新节点 HVs7y/y4xRP/h5gxed/LDnzc/RiZg8/mqP3E，原稿与校准证据见 `docs/ui-design/evidence/learning-assets-{baseline,calibrated}/`。详情设计已包含完整五部分、220 目录、平铺证据/来源和右 380 复习操作栏。

5 个实际页面（列表、输入、详情、结果、报告）×375/768/1024/1440 共 20 张完整截图已生成并逐张 view_image 查看。viewport-checks.json 记录 20/20 无横向溢出、fonts loaded；375 的筛选/操作/模式折行，768 的摘要/复习栏落为单列，1024/1440 目录和宽屏列切换正常，卡片自然滚动。目录、历史、取消、自查与再练入口均可见，截图不是人工产品验收。

字体 CSS 栈以 Noto Sans SC 开头，实际 CDP CSS.getPlatformFontsForNode 对报告标题命中 `PingFangSC-Semibold`，是现有字体回退；不能声称 Noto 实际命中。Pen 画面为顶部导航样例，实际遵循既有个人导航偏好，不能按顶部截图冒称像素一致。选项使用既有 Button/Select、标题/正文由真实结果决定，输入/结果的图标、选中色阶、控件细节与 Pen 静态样例仍有差别；本轮确认布局与功能结构，最终字体/细节视觉由用户验收。Pen bounds 元数据 clipped 与渲染矛盾也保留在设计 README。

截图工具一度 Page.captureScreenshot 超时；同一 TaskSpace 恢复 ego lite 前台后成功，没有新建任务空间、接管用户 tab 或把失败文件冒充证据。详见 `docs/ui-design/evidence/learning-assets-browser/README.md`。

## 尚未完成与边界

用户人工产品/语义/视觉验收未完成；浏览器异常矩阵未逐一制造，自动化覆盖与真实浏览器主流程分别记录。自然长文档及真实私人资料的召回与完整语义质量没有评测，不外推合成样例结论。build、生产部署与 PR 未执行；开发验收阶段未执行 commit/push，用户随后明确授权本次提交并推送。

## Git 交付范围

用户本轮明确要求“提交并且推送代码”。交付本期难点资产/文字精讲源码、测试、迁移、SDK/OpenAPI、运行配置和设计/验收文档；原有无关 `.gitignore` 修改留在工作区。既有自动化结果沿用前文，本次仅复核提交 diff 和远端状态，不追加 build；提交和推送不代表用户人工验收完成。
