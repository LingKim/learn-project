# document-processing Specification

## ADDED Requirements

### Requirement: 有效文件必须自动进入解析

系统 SHALL 在知识库文件完成服务端校验并进入 `pending_processing` 后自动创建幂等文档处理任务，不要求用户再次点击开始。

#### Scenario: 首次校验成功

- **WHEN** PDF、DOCX、TXT 或 Markdown 完成校验并绑定当前用户 FileAsset
- **THEN** 系统创建一个待处理任务并返回“已上传·待解析”
- **AND** 重复处理同一完成事件不得创建多个有效首次解析任务

#### Scenario: 任务排队

- **WHEN** 解析并发已满
- **THEN** 文件保持真实等待状态
- **AND** 前端显示等待处理而不是无限加载或伪造进度

### Requirement: 四类文档必须保留可定位结构

系统 SHALL 解析 PDF、DOCX、TXT 和 Markdown 的受支持文本结构，并为每个分块保存稳定来源锚点。

#### Scenario: 解析有文字层 PDF

- **WHEN** PDF 页面包含可提取正文和内嵌图片
- **THEN** 系统提取正文并保留 1-based 页码
- **AND** 标记页面来源为 `native_text`，不对该页无差别重复 OCR
- **AND** 记录仍未识别的内嵌图片数量，不把图片语义声明为已解析

#### Scenario: 解析扫描 PDF

- **WHEN** PDF 无有效文字层，或正文低于阈值且页面以图片为主
- **THEN** 系统只对待识别页面执行 OCR，按原页序生成正文并保留 1-based 页码
- **AND** 页面来源标记为 `ocr`，记录 OCR provider、策略版本和归一化质量信号
- **AND** 达到质量门禁的结果可以继续分块和索引

#### Scenario: 解析混合 PDF

- **WHEN** 同一 PDF 同时包含可靠文字层页面和扫描页面
- **THEN** 系统分别使用原生提取和页面级 OCR，并按原页序合并结果
- **AND** 同一页只保留一个最终正文来源，不产生原生文本与 OCR 重复分块

#### Scenario: OCR 结果不可用

- **WHEN** OCR 后仍无有效正文、质量低于门禁或超出明确资源上限
- **THEN** 任务确定性失败并分别返回 `DOCUMENT_OCR_NO_TEXT`、`DOCUMENT_OCR_LOW_CONFIDENCE` 或 `DOCUMENT_OCR_LIMIT_EXCEEDED`
- **AND** 文件不得进入可用状态，不得把乱码或不完整草稿写入活动版本
- **AND** 确定性失败不自动重试

#### Scenario: 清理 OCR 中间数据

- **WHEN** PDF OCR 成功、失败或被协作取消
- **THEN** 页面渲染图和 OCR 中间文件被清理
- **AND** 普通日志、Trace 和长期对象存储不保留页面图像或 OCR 正文副本

#### Scenario: 解析 DOCX

- **WHEN** DOCX 包含标题、普通段落、列表、表格和图片
- **THEN** 系统按文档顺序提取受支持文本并保留标题路径与段落范围
- **AND** 记录图片数量
- **AND** 不伪造页码，不解析批注、修订历史、图片文字、嵌入附件或页眉页脚

#### Scenario: 解析 Markdown

- **WHEN** Markdown 包含标题、段落、列表、表格、代码块和图片引用
- **THEN** 系统保留块级结构与标题路径
- **AND** 只使用可信非空 alt 文本作为图片上下文
- **AND** 不访问远程 URL、相对路径或 data URI 图片

### Requirement: 分块必须感知结构并版本化

系统 SHALL 优先沿标题、段落、列表、表格和代码块边界分块，只在结构单元超长时二次切分，并将目标长度、最大长度、重叠和清洗规则记录为策略版本。

#### Scenario: 超长段落

- **WHEN** 单个段落超过当前策略最大长度
- **THEN** 系统按配置切分并保留少量重叠
- **AND** 每个子块继承相同标题路径和准确段落来源

#### Scenario: 表格分块

- **WHEN** 表格不能放入一个块
- **THEN** 系统按相邻行组拆分
- **AND** 每个块保留理解数据所需的表头

#### Scenario: 代码块

- **WHEN** Markdown 代码块不超过最大长度
- **THEN** 系统将其作为完整结构单元
- **AND** 不在任意行中间切断代码块

### Requirement: 解析结果必须按用户和版本隔离

系统 SHALL 将解析结果归属于用户级 FileAsset 与处理版本。同一用户多个知识库关联可以复用兼容活动版本；不同用户不得共享正文、分块、向量或检索结果。

#### Scenario: 同用户跨知识库关联

- **WHEN** 当前用户将已有 FileAsset 关联到另一个知识库
- **THEN** 新关联复用该 FileAsset 的兼容活动解析版本
- **AND** 不重复下载、解析或生成向量

#### Scenario: 跨用户相同摘要

- **WHEN** 两个用户的文件复用相同 StoredObject
- **THEN** 两个用户分别拥有独立处理版本、分块和向量
- **AND** 任一用户不能通过任务、错误或检索推断另一用户的解析状态

### Requirement: 重新解析必须原子发布

系统 SHALL 在草稿版本中完成重新解析，新版本全部成功后才原子切换活动版本。

#### Scenario: 重新解析成功

- **WHEN** 已有可用文件的新处理版本完成全部正文和分块写入，并完成 Qdrant 向量 upsert、确认和数量校验
- **THEN** 系统在短事务中切换活动版本
- **AND** 后续检索只使用新版本
- **AND** 旧版本进入可清理状态

#### Scenario: 重新解析失败或取消

- **WHEN** 新处理版本失败或被取消
- **THEN** 旧活动版本继续可用
- **AND** 未发布草稿不会进入检索
- **AND** 页面显示最近重新解析失败或取消，而不是把文件整体标为不可用

#### Scenario: Qdrant 写入成功但 PostgreSQL 发布失败

- **WHEN** 草稿版本的向量 point 已写入 Qdrant，但 PostgreSQL 活动版本事务没有提交
- **THEN** 这些 point 因不属于 PostgreSQL 当前活动版本而不可检索
- **AND** 系统创建或保留幂等清理任务回收孤儿 point
- **AND** 不宣称 Qdrant 与 PostgreSQL 存在跨库 ACID

### Requirement: 删除与移动必须立即影响检索归属

系统 SHALL 根据有效 KnowledgeBaseFile 关联控制检索范围，移动不重建解析，删除立即撤销对应知识库检索能力。

#### Scenario: 移动文件

- **WHEN** 用户把文件从知识库 A 移动到知识库 B
- **THEN** 文件不再出现在 A 的检索结果中并可在 B 中检索
- **AND** 不重新创建处理版本或向量

#### Scenario: 删除最后一个关联

- **WHEN** FileAsset 最后一个有效知识库关联被删除
- **THEN** 系统在 PostgreSQL 事务中阻止新处理结果发布、撤销活动版本并创建持久化 Qdrant 清理任务
- **AND** 后续检索通过当前允许范围与返回前复核立即排除该文件，不等待 Qdrant 物理删除
- **AND** 清理 worker 幂等删除草稿与活动版本 point，周期对账修复孤儿或遗漏
- **AND** 现有物理对象删除继续由文件清理编排按引用事实执行


### Requirement: OCR 文本质量门禁必须支持技术文档 Unicode 符号

系统 SHALL 将合法 Unicode 标点、数学符号和组合字符纳入可读文字检查，不得因为公式、箭头或弯引号而误判有效技术文档为识别质量不足；空白、纯符号、替换乱码及大量控制/私用字符 SHALL 继续拒绝。

#### Scenario: 技术课件包含公式

- **WHEN** OCR 返回正常文字、数学符号 Sm 与弯引号 Pi/Pf，且没有乱码替换字符
- **THEN** 质量检查接纳 Unicode 字符类别 M/P/S，不使用固定 ASCII 标点白名单
- **AND** 保留原文与原页码继续索引，不伪造供应商置信度

#### Scenario: 内容没有可用文字

- **WHEN** OCR 返回纯符号、空白、乱码替换字符或大量控制/私用字符
- **THEN** 系统继续阻止发布，保持明确失败分类
