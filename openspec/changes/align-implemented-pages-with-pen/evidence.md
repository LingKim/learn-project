# 页面修正验收记录

日期：2026-10-02。依据先于实现的proposal/design/spec、Pen实时图层及既有核查报告。未改Pen设计。修正了全局颜色与导航、登录/注册、学习室、内容库总览/文件管理/删除确认和个人资料。当前PRD优先：用户名认证、画像字段、固定会话来源保持现有业务；未实现模块禁用。

## 实际浏览器核对

使用ego-browser同一任务空间8，在本轮隔离8092 API/3102前端、唯一临时DB/buckets/collection和合成账号下核验。资料仅为run_document_smoke.py合成的四格式样本；真实千问只收到合成问题及notes.txt中公开常识文本。最后补充3000未登录页的登录响应布局，未浏览业务资料。

| 页面 | 1440×960实际DOM | 390/768结果 |
| --- | --- | --- |
| 登录 | 品牌520px、form420px、品牌标题40px | form350/420px、无横向溢出 |
| 注册 | 品牌460px、form460px、品牌标题40px | form350/460px、无横向溢出 |
| 学习空状态 | 顶栏76px；侧栏x0/y76/w312/h884，rgb(244,238,220)；标题26px | 侧栏纵向、无横向溢出 |
| 有对话 | 用户右侧rgb(240,240,236)；AI浅黄按Pen颜色实现，独立输入区；来源摘要固定 | 390/768/1440均无横向溢出 |
| 内容库 | 顶栏76px、标题24px；真实统计1知识库/4可用/0处理中/默认知识库最近更新 | 无横向溢出 |
| 文件管理 | 标题23px；文件名/格式/状态/更新时间/操作5列，4格式样本 | 无横向溢出，表格内部可滚动 |
| 删除确认 | Dialog x0/y76/w1440/h884，保留顶栏；标题与影响摘要/范围/按钮 | 取消恢复原列表上下文；未提交删除 |
| 个人资料 | 设置栏220px，gap40px；padding120px；实际form925px（1440视口纵向滚动条占15px） | 平面纵向布局，无横向溢出 |

实际交互：用户名登录；真实资料汇总；PDF筛选只返回notes.pdf；删除确认打开/取消；资料昵称保存成功；三学习模式仅快速回答可用；资料chips加载并选择notes.txt；独立AI说明勾选确认；真实通用回答、反馈持久化、追问focus到learning-question；固定范围摘要；无依据问题拒答；有依据问题回答带[1]notes.txt引用，打开预览显示原合成资料。未本轮实测头像上传/冲突、会话重命名/删除、完整失败/超时/处理中视觉状态；既有自动测试不替代这些视觉验收。

## 自动化验证

- 前端pnpm check：Oxfmt、API边界、Oxlint、TypeScript、Vitest、OpenAPI client一致性检查通过，62 tests passed（18 files）。新增安全答案呈现（HTML/script/link均文本、代码围栏/强调）测试；格式/排序Query key及SDK参数、统计统一解包测试。
- 后端Ruff、mypy（66 source files）通过；pytest常规133 passed/16 skipped。跳过项要求隔离DB或真实模型环境，未计作通过。local Qdrant的payload index警告为测试本地引擎限制。
- run_learning_checks.py隔离集成14 passed/1 skipped（真实模型专项），包含新增统计所有权/知识库和文件软删除排除、大小写格式过滤、分页前筛选/稳定名字排序、状态交集、跨用户知识库访问拒绝。临时DB已DROP，collection清理。
- 四格式driver HTTP权限矩阵、检索与trace通过；本轮浏览器真实千问的合成通用/资料回答为独立证据，不扩称完整生成质量评测。
- OpenSpec strict通过；git diff --check通过；没有运行Next/Docker build，没有commit/push。

## 服务与清理

本地8000仅优雅重载受管backend（新PID27220），其余本地workers和3000保持运行，未启停外部PostgreSQL/Redis/Qdrant/RustFS。`/api/v1/health/live`、`ready`为200，未登录统计接口401。无业务库DDL。隔离driver最终输出DROP DATABASE及isolated resources cleaned；浏览器task8 finish完成；tsconfig自动新增的.next-learning-e2e include已精确移除。

## 验收边界

实际页面截图ego Page.captureScreenshot超时（此前Pen内置截图同样超时），没有可用本轮截图文件。已按Pen图层核对上述结构/尺寸与颜色，但未完成逐像素、字体实际命中、完整色差和全部状态截图验收，不能宣称严格视觉验收全部通过。Noto Sans SC为首选、系统字体兜底，没有下载字体。用户人工验收仍待完成。
