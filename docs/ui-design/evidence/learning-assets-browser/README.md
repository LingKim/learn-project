# 浏览器与视觉核验

2026-10-03，单一 ego-browser TaskSpace 15，p1/p2。本人合成样例，不选择或外发用户资料，原练习历史保留。

列表、输入、难点详情、精讲结果、练习报告分别为 list/input/detail/result/report。每页截图 `*-375.png`、`*-768.png`、`*-1024.png`、`*-1440.png`，共 20 张，均已通过 view_image 实际查看。截图使用真实卡片/证据/报告，而非 mock 页面；输入/模式/筛选/操作折行、目录与单列/宽屏布局均已查看。viewport-checks.json 记录无横向溢出与字体加载状态。早期 weakness-detail-1440.png 是 v1 基线，最终以 detail-1440.png 为准。

通过 CDP CSS.getPlatformFontsForNode 核对报告 h1，实际命中 PingFangSC-Semibold；CSS 声明以 Noto Sans SC 开头不等于实际使用 Noto。沿用已有字体回退，不声称与 Pen 字体/每像素一致。Pen 为顶部导航样例，实际跟随用户现有导航偏好；静态设计与真实数据高度、既有 Button/Select、图标及选中色阶存在细节差异，最终由用户视觉验收。

业务主闭环已实际验证：手动难点→真实精讲v1→针对性3题保存/提交→报告3/3正确→真实复习记录；已有正式难点复用精讲并保留配置生成v2、刷新恢复、历史v1、取消后保留v2；独立直接精讲v1/v2不新增难点；手动掌握/恢复学习中后profile活动列表同步。低置信度/失效来源/网络响应丢失/失败重试由自动化覆盖，没有逐项制造浏览器反例。

Page.captureScreenshot 曾持续超时；同一 TaskSpace 恢复 ego lite 前台后，20 张截图成功完成，未新建空间或绕过用户接管。用户人工验收尚未完成。完整实现、测试、迁移、模型分母与ID见 openspec/changes/implement-learning-assets/evidence.md。
