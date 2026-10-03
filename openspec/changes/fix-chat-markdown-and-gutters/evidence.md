# 2026-10-03 Markdown与边距验收补正

## 根因和实际修正

用户截图的watch回答不是合法块Markdown。只读指定会话/问题确认1647字符、0实际换行、0字面\n、12代码围栏，标题与围栏粘连；标准react-markdown不能推断已丢失的代码换行。上轮合法Markdown样例通过不代表此模型输出也正确。

用户随后明确授权“历史数据有问题可以清掉，后续没问题就行”。取消了历史normalizer，准确撤回helper与调用/测试，未猜测改写代码。执行清理时限定验收账号昵称、vue3计算属性会话、watch怎么用问题、succeeded状态，并锁定单条0换行12围栏记录；删除前全部字段备份到Git忽略的.runtime目录（0600），删除1条并读回确认，同会话另2条正常记录保留。真实浏览器重新读取该会话turns=2，removedTargetAbsent=true。未清全部账号或正常历史，没有业务schema迁移。

生成Prompt片段升v4：要求标题、段落、围栏和代码行保持标准换行并正确JSON编码。守卫拒绝强格式损坏信号及未闭合围栏，返回ANSWER_MARKDOWN_INVALID；不保存为成功答案、可同key重试，不自动猜测补写代码或外发历史。自审又补普通#解释误拒、字面双重转义换行、html语言粘代码的回归；合法代码/inlinecode/HTML/路径保留。失败回归曾真实出现4个失败，审查回归另有3个失败，修复后全部通过。

布局根因是mx-auto+900px外层行再嵌808px AI上限，并叠列表40px边距；宽屏重复窄列留白明显。移除居中外层上限，列表仅桌面24px/窄屏16px边距，AI靠左、用户靠右，气泡采用比例和宽度上限。继续保持Pen ehMic的顶栏76/侧栏312/顶部125/输入88、头像36与间距12；旧650/760绝对正文宽度由本轮明确要求的响应式宽度取代。实际再次读Pen07，1440×960、顶栏1440×76、工作区1440×884、侧栏312×884、主区1128×884。

## 真实模型和浏览器

当前Qwen qwen3.8-flash仅接收合成Vuewatch技术问题，未接收历史正文/用户业务资料。新版Prompt真实输出234段delta、101个换行、8围栏（4完整代码块），耗时11.38s；流式累积与最终正文逐字符一致，格式校验通过。

用该真实输出的临时本地预览调用实际AnswerContent组件：浏览器6标题、4个pre/code块，代码行数9/11/28/22，未横向溢出。实际截图见 [watch-markdown.png](screenshots/watch-markdown.png)。这是生成端真实结果+实际renderer的组合验证，未宣称本轮这个新样例经过完整HTTP持久化链路；坏终态不落库由隔离集成测试独立验证。临时路由已删除。

真实本地聊天页面1440/1920：AI外层距消息区左边24px，用户距右边39px（包含15px滚动条，内容边距24px）；390宽AI/用户均16px。三宽无页面横向溢出，用户原浏览器标签未接管、未强制刷新。

## 检查和清理

- 最终frontend pnpm check通过：Oxfmt/API边界/Oxlint/TypeScript/79测试（19文件）/OpenAPI一致性。渲染原7测试保留通过，未引入历史兼容。
- backend最终153 passed / 26 skipped，Ruff/mypy 66 source files通过；新增格式相关generation37测试通过。skip需要隔离DB或真实模型条件，未计作通过。本地Qdrant payload index提示为本地引擎限制。
- run_learning_checks.py唯一临时DB/collection24 passed / 1 skipped，新增坏Markdown最终校验失败不存正文、同key重试成功；不把真实模型专项skip当通过。
- OpenSpec strict、git diff --check通过，未运行build，未commit/push。
- 受管8000后端优雅重载为PID58532，live/ready均200；3000保持dev/HMR，其他worker与外部基础设施未启停。
- 隔离serve与集成DB均DROP/清理；临时预览删除，tsconfig测试include精确恢复；浏览器task10 finish完成。
- 用户人工验收待完成；本轮只处理聊天页面和格式生成规则，不声明全产品视觉/字体/逐像素验收。
