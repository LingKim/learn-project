# Tasks：难点资产与文字知识精讲第一版

## 1. 方向与方案

- [x] 用户确认下一开发方向（“好的 确认”，不等同具体方案批准）
- [x] 核对 PRD、源码、已有刷题 tasks/evidence、Git 与现有领域/契约
- [x] 读取 Pen 08/09/38/39 图层/文字/渲染并导出原稿，记录未交付入口与状态差异
- [x] 编写 proposal/design/API草案/spec/tasks/evidence，并同步PRD分期状态
- [x] 独立subagent只读方案自审、处理具体缺口
- [x] OpenSpec strict validate与文档diff检查
- [x] 展示范围、默认门槛、状态与验收标准，用户于2026-10-03回复“开始开发”明确批准

## 2. 设计与契约冻结

- [x] 按批准方案校准Pen输入/结果/列表/详情与练习报告，补候选/空/失败/取消状态
- [x] 冻结Pydantic输入输出、内容预算、错误与owner/版本/来源契约
- [x] 固定识别/验证策略版本及边界样例，建立不重复计数/忽略/重评规则
- [x] 明确主agent与前后端subagent文件归属，共享practice/profiles/SDK由主agent集成

## 3. 后端与运行

- [x] 实现Weakness/证据/追加事件/评分与完成/删除outbox、私有CRUD与状态转移
- [x] 实现最新提交/评分取值、distinct题目/30天窗口/重复门槛、候选确认/忽略/撤销
- [x] 实现精确去重及并发幂等、重评supersede、来源失效和不自动复活
- [x] 实现KnowledgeExplanation/不可变卡片/KnowledgeRun、知识worker与202查询恢复
- [x] 实现权限/检索/结构化生成/五部分内容与引用/发布再校验，拒绝资料不足
- [x] 实现卡片失败保留、版本读取、租约心跳/超时/取消/重启/迟到结果保护
- [x] 接入难点或精讲卡片targeted PracticeConfig/Review追加版本与实际验证分母，保护普通练习兼容
- [x] 接入profiles真实活动难点和字段级上下文，禁止自动回写画像
- [x] 接入本项目运行命令/Settings，日志不含正文和Prompt
- [x] 隔离迁移upgrade/downgrade/upgrade；业务库写前目标/current/可恢复备份，写后读回版本/API

## 4. 前端与集成

- [x] 真实后端API权限与失败门禁通过后导出OpenAPI并生成SDK
- [x] 通过feature API/queryOptions/mutationOptions/shared ApiError接入难点与精讲
- [x] 实现候选确认/忽略、难点筛选/详情/编辑/撤销/状态/软删除与证据历史
- [x] 实现精讲输入/五部分结果/引用/历史/卡片版本/真实任务/取消重试
- [x] 接入学习模式、当前导航偏好、报告入口及难点预填练习，不丢失模式草稿
- [x] 实现来源失效原文cache清理、并发输入保留与刷新恢复

## 5. 自审与验证

- [x] 规则边界、objective/subjective事件、outbox重放、重评修正、ignore/revoke与状态测试
- [x] 权限矩阵/失效来源/私有历史/版本冲突/迟到发布与取消竞争真实接口测试
- [x] 非目标普通练习及快速回答回归，迁移与worker重启恢复测试
- [x] 合成六格式（TXT/MD/DOCX/原生/扫描/混合PDF）精讲评测；结构/引用/无依据拒绝真实分母及人工语义抽样
- [x] 前端组件/Query/cache/草稿/错误/刷新恢复验证
- [x] Ruff/mypy/pytest、Oxfmt/Oxlint/TypeScript/Vitest、API边界/OpenAPI与OpenSpec检查
- [x] 本人浏览器主闭环：手动难点、直接精讲、3题再练/报告、历史版本、刷新/取消及profile状态联动
- [ ] 浏览器异常矩阵逐一复现：低置信度、失效来源、响应丢失及失败重试（对应自动化已通过，不能替代此项）
- [x] 375/768/1024/1440五页20张截图逐张检视及Pen结构核对，记录实际字体回退/细节差异，未冒称像素一致
- [x] 主agent与独立只读自审，更新evidence与任务状态，准确报告未验证项
- [ ] 用户人工产品/语义/视觉验收；字体回退和控件细节差异见evidence
- 开发验收阶段未运行 build 或执行 commit/push/PR。用户随后明确授权本次提交并推送；人工验收保持未完成。
