## ADDED Requirements

### Requirement: Evidence based weakness candidates
系统 SHALL 从本人练习的最新有效提交与评分建立候选薄弱点，绑定不可变题目、回答、评分和策略版本，不把单次答错当长期能力结论。

#### Scenario: One wrong answer
- **WHEN** 一道题的有效评分为错误或部分正确
- **THEN** 建立可确认候选并展示证据，不因一次错误自动成为正式难点

#### Scenario: Repeated question and regrading
- **WHEN** 同一道题重复作答或同一提交重评
- **THEN** 按独立question计数并以最新提交/成功评分更新当前证据，旧版本保留，不累加成多道题

#### Scenario: Unreliable or missing grading
- **WHEN** 提交未评分、评分失败或主观结果为低置信度
- **THEN** 不用于自动入库、系统验证通过或自动状态回退，低置信度候选仍可由本人确认

#### Scenario: Multi topic attribution unavailable
- **WHEN** 一道题涉及多个知识点但没有可靠逐知识点评分映射
- **THEN** 仅展示归因未验证的待确认候选，不把总体结果作为每个知识点的自动入库/验证证据

### Requirement: Versioned automatic admission policy
系统 SHALL 用已批准的重复错误、题目难度、近期表现与评分可靠性门槛决定自动入库，保存策略版本并显示实际证据。

#### Scenario: Sufficient repeated evidence
- **WHEN** 同一概念/来源范围满足proposal中待批准的30天/不同题/不同练习/难度/近期结果门槛
- **THEN** 幂等创建或关联一个正式难点，首次生成卡片仅入队一次，不声称统计掌握概率

#### Scenario: Pending candidate decision
- **WHEN** 用户确认或忽略不满足自动门槛的候选
- **THEN** 保存明确决定，确认入队首次卡片，忽略的旧证据事件不反复重现

#### Scenario: Corrected evidence
- **WHEN** 最新重评修正先前错误
- **THEN** 追加修正历史并替代当前证据，不删除已确认资产或改写旧报告，支持不足明确标记

### Requirement: Durable private evidence ingestion
系统 SHALL 与评分发布、练习完成及来源练习删除同事务记录持久事件，以可重启幂等消费更新资产/复习，GET不产生识别或状态副作用。

#### Scenario: Worker restart and duplicate event
- **WHEN** 评分完成后worker重启或同一事件重复消费
- **THEN** 已提交事件可继续处理，唯一约束阻止重复证据、正式资产和首次卡片任务

#### Scenario: Objective grading
- **WHEN** 客观题同步判分或主观题异步发布成功
- **THEN** 两条真实链路均记录评分事件，不能只覆盖主观worker

#### Scenario: Completion after grading event consumed
- **WHEN** 最后一题评分事件已处理后用户完成练习
- **THEN** 完成事务的持久事件仍触发最终复习结论，不依赖GET或后续评分才能显示通过

### Requirement: Private asset lifecycle
系统 SHALL 提供本人候选与正式难点的独立决定状态、掌握状态、编辑、撤销、软删除和追加历史，精确去重不进行未经确认的语义合并。

#### Scenario: Equivalent and different scopes
- **WHEN** 同一owner在同一来源范围识别规范化同名概念，或在不同知识库/选中文件集合发现同名概念
- **THEN** 前者幂等关联已有活动项，后者不静默合并跨来源证据

#### Scenario: Manual learning target
- **WHEN** 本人手动创建概念与明确来源范围
- **THEN** 保存manual声明/确认快照，可作为活动学习目标，不伪造grade或参与自动错误/系统验证门槛

#### Scenario: Change source scope
- **WHEN** 用户需要切换难点的模式/知识库/文件集合
- **THEN** 首版创建新的直接精讲或手动难点，不改变旧资产逻辑来源键、证据和历史练习；同范围采用当前处理版本需显式新生成

#### Scenario: Revoked or deleted asset
- **WHEN** 本人撤销或软删除难点
- **THEN** 保留历史及原练习，停止未发布卡片，旧事件不自动复活资产

#### Scenario: Concurrent modification
- **WHEN** 陈旧expected_version编辑名称、决定或掌握状态
- **THEN** 返回版本冲突，保留用户输入，不覆盖新版本

### Requirement: Structured textual explanation
系统 SHALL 为正式难点或用户主动指定知识点提供结构化文字精讲，包含概念/适用场景、原理、示例、误区和理解练习，保存不可变卡片版本。

#### Scenario: Unconfirmed and confirmed candidate
- **WHEN** 候选仍待确认或正式入库
- **THEN** 前者不生成卡片，后者仅入队一次首次生成，直接精讲不隐式创建难点

#### Scenario: Regeneration failure
- **WHEN** 用户重新生成但模型或质量门禁失败
- **THEN** 记录失败run并保留旧活动卡片，成功新结果只创建新版本

#### Scenario: General explanation
- **WHEN** 用户明确选择通用模式
- **THEN** 标明模型通用知识，不虚构资料引用、用户经历或实际代码执行结果

### Requirement: Grounded materials and revocation
系统 SHALL 复用当前owner范围的受保护检索生成资料精讲，在执行与发布时校验来源、目标及版本。

#### Scenario: Evidence insufficient
- **WHEN** 资料不能支持必要讲解或引用不在允许证据内
- **THEN** 拒绝发布，不静默切换通用模式或扩大文件范围

#### Scenario: Source changes during generation
- **WHEN** 文件删除、移动、重解析或活动版本变化
- **THEN** 阻止陈旧结果发布，不返回失效来源原文；本人已保存业务卡片按历史规则保留并标明来源不可用

#### Scenario: Deleted originating practice
- **WHEN** 难点来源练习被软删除
- **THEN** 资产详情不能绕过删除返回其题目/回答原文，不可用证据不参与自动识别与验证

### Requirement: Targeted practice and review evidence
系统 SHALL 从用户选中难点创建新的关联练习，复用已有配置确认、题集、答案和评分，按真实相关题覆盖建立追加复习记录。

#### Scenario: Start targeted practice
- **WHEN** 用户从单个难点进入再练流程
- **THEN** 固化难点/来源版本并预填可编辑配置，不自动开始或覆盖原attempt，未选择难点的普通练习保持兼容

#### Scenario: Practice from direct explanation
- **WHEN** 用户从未关联难点的直接精讲卡片进入再练
- **THEN** 使用explanation/id/card_version目标创建新练习和卡片复习记录，不隐式创建难点或更新掌握状态

#### Scenario: Explicit target configuration mismatch
- **WHEN** 用户保留学习目标却明确修改为不兼容的主题或来源范围
- **THEN** plan前返回配置冲突并保留输入，用户可显式移除关联作为普通练习，系统不覆盖输入或伪造topic

#### Scenario: Successful verification
- **WHEN** 完成的关联练习相关单知识点题总数至少3道且每道已提交、有效评分、全部正确、无低置信度
- **THEN** 记录本次验证通过和实际分母，由用户决定标记已掌握，不推断永久掌握

#### Scenario: Incorrect or incomplete review
- **WHEN** 待验证/已掌握难点的关联练习出现有效错误，或只有未提交/未评分/低置信度结果
- **THEN** 前者按批准规则回到学习中，后者不生成成功或失败掌握结论，实际缺失覆盖明确展示

#### Scenario: Review regrading
- **WHEN** 完成练习的评分被重评或目标随后编辑
- **THEN** 追加复习结果版本，旧目标/题集/评分保持稳定，撤销目标不继续自动更新状态

#### Scenario: Delayed older evidence after manual state change
- **WHEN** 旧回答或旧练习事件在用户后来手动修改掌握状态之后消费
- **THEN** 依据原回答时间与目标当前版本追加复习结论，不将迟到处理当作新错误覆写用户后来的状态

### Requirement: Selected asset context and profile boundary
系统 SHALL 从真实领域读取本人有证据的活动难点，并逐字段应用本次输入、选中资产、画像、默认值优先级。

#### Scenario: Omitted and explicitly cleared context
- **WHEN** 用户省略可兜底字段或显式清空字段
- **THEN** 仅省略字段允许兜底，明确清空不被补回，不回写画像，不注入未选择难点

#### Scenario: Activity view
- **WHEN** 用户读取个人资料活动薄弱点
- **THEN** 查询真实owner领域对象，排除撤销/删除/已掌握与无有效证据项，不返回预置假列表

### Requirement: Bounded private knowledge runs
系统 SHALL 用持久202、request_key/input_digest、租约token、对象版本和权限/来源再校验保护生成，不制造虚假文件或题集关联。

#### Scenario: Lost response and repeated operation
- **WHEN** 初始响应丢失或相同key重放
- **THEN** 本人可恢复真实run，相同输入复用结果，不同输入冲突，不重复发布卡片

#### Scenario: Cancel, timeout and stale lease
- **WHEN** 用户取消、租约过期、对象撤销或迟到模型返回
- **THEN** 保留旧业务结果，过期token不能发布，重启后pending可继续，failed明确重试

### Requirement: Privacy and generated contract
系统 SHALL 使用FastAPI生成契约、统一响应/错误和feature API/Query，禁止非owner及管理员读取用户业务正文。

#### Scenario: Cross owner or administrator
- **WHEN** 非owner猜测资产/卡片/证据/run ID
- **THEN** 返回404，日志和管理员界面不泄露正文、画像、Prompt或凭据

#### Scenario: Revoked source cache
- **WHEN** 页面查询得知来源不可用或对象删除
- **THEN** 清除受影响预览原文cache，不仅禁用按钮而保留原文

### Requirement: Design fidelity and measured quality
系统 SHALL 在实施前校准已读取Pen原稿，分别验证自动规则、卡片质量、浏览器和视觉，不以文档存在代替交付。

#### Scenario: Design alignment
- **WHEN** 校准08/09/38/39及练习报告
- **THEN** 保留对应布局并移除未批准入口，补本期状态，逐项核验375/768/1024/1440布局/文案/字体/交互

#### Scenario: Quality evaluation
- **WHEN** 用合成四格式及三类PDF验证精讲
- **THEN** 报告结构/引用/无依据拒绝的真实分母、失败和人工语义抽样，目标见proposal，小样本不称生产质量全面通过
