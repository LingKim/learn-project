# File Upload and Storage Specification

## Requirement：上传会话必须绑定业务范围

系统 SHALL 只允许已认证用户通过自己知识库的业务接口创建文件上传会话；所有者、知识库、用途、存储域、策略版本和保留规则 SHALL 由后端确定。客户端 SHALL NOT 指定用户 ID、bucket、object key、安全等级或保留期。

### Scenario：为自己的知识库创建会话

- **WHEN** 用户为自己有效的知识库提交合法文件元数据和新的幂等键
- **THEN** 系统创建绑定该用户、知识库和策略快照的 24 小时上传会话
- **AND** 返回单次或 multipart 上传计划

### Scenario：为其他用户知识库创建会话

- **WHEN** 用户提交不属于自己的知识库 ID
- **THEN** 系统返回 404 或等价的不泄露响应
- **AND** 不创建上传会话或 RustFS multipart

## Requirement：上传传输必须支持续签和分片

不超过 20 MB 的文件 SHALL 使用单次预签名 PUT；超过 20 MB 的文件 SHALL 使用 16 MB multipart。有效会话 SHALL 支持续签和断点续传，签名过期 SHALL NOT 改变会话业务身份。

### Scenario：小文件上传

- **WHEN** 声明大小不超过 20 MB 且满足当前策略
- **THEN** 系统返回 15 分钟有效的单次上传地址
- **AND** 完成前不创建可下载的业务文件

### Scenario：multipart 续传

- **WHEN** 有效 multipart 会话的部分分片已成功且签名过期
- **THEN** 用户可以查询已有分片并为剩余分片续签
- **AND** 续签不得修改文件名、大小、用途、用户或知识库

### Scenario：会话过期

- **WHEN** 上传会话超过 24 小时仍未完成
- **THEN** 系统将其标记为 EXPIRED 并拒绝完成或续签
- **AND** 生成残留分片或临时对象清理任务

## Requirement：服务端摘要与真实文件验证是安全边界

系统 SHALL 在上传完成后从隔离存储流式读取对象并计算 SHA-256，复核实际字节数、真实类型和结构；客户端扩展名、MIME、MD5、SHA-256 和 multipart ETag SHALL NOT 成为可信唯一性或安全判断。

### Scenario：合法知识库文件

- **WHEN** PDF、DOCX、TXT 或 MD 的实际类型、大小和结构满足会话策略快照
- **THEN** 系统保存 64 位小写服务端 SHA-256 并允许对象提升
- **AND** 文件业务状态为“已上传·待解析”而不是“可用”

### Scenario：伪造扩展名

- **WHEN** 文件扩展名或声明 MIME 与真实签名和结构不一致
- **THEN** 系统拒绝文件并返回稳定校验错误
- **AND** 隔离对象进入清理任务且不得创建有效业务关联

### Scenario：不支持的危险结构

- **WHEN** 文件损坏、加密、包含宏、PDF 嵌入附件、异常压缩比、异常解压体积或文本 NUL 字节
- **THEN** 系统拒绝该文件
- **AND** 不执行未受控宏、脚本或嵌入内容

### Scenario：病毒扫描能力边界

- **WHEN** 系统完成格式、结构和资源限制校验
- **THEN** 系统不得将结果描述为“病毒扫描通过”
- **AND** 首期不得依赖不存在的病毒扫描服务或状态

## Requirement：文件策略必须有默认值与硬上限

系统 SHALL 对每个上传用途使用版本化策略，并在创建会话时固化快照。管理员 SHALL 只能在系统硬上限内发布规则；普通规则变化 SHALL 只影响新会话。

### Scenario：管理员收紧大小限制

- **WHEN** 管理员发布新的有效策略
- **THEN** 新会话使用新限制
- **AND** 既有会话仍使用创建时快照，既有有效文件不自动失效

### Scenario：超过系统硬上限

- **WHEN** 管理员草稿包含超过硬上限的大小、页数、字符、时长或容量
- **THEN** 系统返回 422
- **AND** 不允许发布该版本

## Requirement：稳定性保护必须在后端执行

系统 SHALL 默认限制每用户同时 3 个上传会话、每小时 30 个新会话、未完成上传 2 GB、长期文件 10 GB，并提供不可突破的系统硬上限；这些限制 SHALL NOT 被表现为商业套餐额度。

### Scenario：并发会话达到上限

- **WHEN** 用户已有 3 个有效上传中会话又创建新会话
- **THEN** 系统返回 429 和稳定错误码
- **AND** 不创建临时对象或 multipart

### Scenario：单文件超过策略

- **WHEN** 声明或完成后的实际文件大小超过会话策略
- **THEN** 系统返回 413 或将完成会话标记为确定性失败
- **AND** 超限对象进入清理任务

## Requirement：物理对象与用户所有权必须隔离

系统 SHALL 分离 StoredObject 与 FileAsset。兼容存储域内相同服务端 SHA-256 和字节数可以复用物理对象，但每个用户 SHALL 拥有独立逻辑资产，且不得跨用户共享权限、业务关联、解析结果、分块或向量。

### Scenario：两个用户上传相同字节

- **WHEN** 不同用户上传 SHA-256 和字节数相同且存储域兼容的文件
- **THEN** 系统可以复用同一 StoredObject
- **AND** 为每个用户创建独立 FileAsset，不向任一用户暴露跨用户命中

### Scenario：一个用户删除共享文件

- **WHEN** 用户删除自己的最后一个业务关联但其他用户仍有有效 FileAsset
- **THEN** 系统删除当前用户的逻辑资产和访问能力
- **AND** 不物理删除仍被其他用户合法引用的 StoredObject

## Requirement：上传写操作必须幂等

创建会话 SHALL 支持 24 小时 `Idempotency-Key`；完成、取消和重复选择 SHALL 幂等。数据库唯一约束和摘要级串行化 SHALL 防止并发创建重复物理对象或重复引用。

### Scenario：重复完成同一会话

- **WHEN** 客户端因网络重试多次提交相同完成请求
- **THEN** 系统返回同一最终结果
- **AND** 不重复创建 FileAsset、KnowledgeBaseFile 或增加引用计数

### Scenario：幂等键复用不同正文

- **WHEN** 同一用户在同一接口用同一幂等键提交不同请求正文
- **THEN** 系统返回 409 `IDEMPOTENCY_KEY_REUSED`
- **AND** 不覆盖原请求或创建新副作用
