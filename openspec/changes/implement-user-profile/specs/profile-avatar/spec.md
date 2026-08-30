# profile-avatar Specification

## Requirements

### Requirement：头像必须使用独立受控文件用途

系统 SHALL 通过服务端创建的 `avatar` purpose 上传会话接收头像，复用 UploadSession、StoredObject 和 FileAsset，但 SHALL NOT 创建 KnowledgeBaseFile 或进入文档解析与 RAG 流程。

#### Scenario：创建头像上传会话

- **WHEN** 当前普通用户提交允许的文件名、大小和客户端类型声明
- **THEN** 系统按当前活动 avatar 策略创建范围固定的上传会话
- **AND** 所有者、purpose、bucket、object key 和限制快照由服务端决定

#### Scenario：客户端覆盖文件范围

- **WHEN** 客户端尝试指定其他用户、knowledge base、purpose、bucket 或 object key
- **THEN** 系统拒绝未知或越权字段
- **AND** 不创建可用于其他业务的上传会话

#### Scenario：完成头像上传

- **WHEN** avatar 上传会话完成服务端复核
- **THEN** 系统进入头像校验与转换状态
- **AND** 不创建 KnowledgeBaseFile、解析任务、分块或向量

### Requirement：头像必须通过真实图片与资源边界校验

系统 SHALL 只接受真实 JPEG、PNG 或静态 WebP，并在处理前后校验字节大小、真实 MIME、解码结果、宽高、总像素、帧数和处理超时；默认最大 5 MB。

#### Scenario：合法静态图片

- **WHEN** 服务端检测到格式、大小、尺寸、像素和单帧均符合策略的图片
- **THEN** 系统允许进入转换

#### Scenario：扩展名或 MIME 伪装

- **WHEN** 文件扩展名或客户端 MIME 声称为图片但服务端无法按允许格式解码
- **THEN** 系统返回稳定 `AVATAR_INVALID_IMAGE`
- **AND** 不切换当前头像

#### Scenario：动画或资源异常图片

- **WHEN** 图片为动画/多帧、损坏、超出尺寸或像素上限、触发解码资源或超时限制
- **THEN** 系统拒绝处理并记录稳定错误码
- **AND** 不在错误或日志中暴露解析器原始异常和元数据

### Requirement：服务端必须生成去元数据的统一方形 WebP

系统 SHALL 应用图片方向后清除 EXIF 等非必要元数据，并使用确定裁剪策略生成统一 512×512 静态 WebP；业务头像引用 SHALL 指向派生文件而非原始上传对象。

#### Scenario：转换横向图片

- **WHEN** 用户上传符合策略的横向图片
- **THEN** 系统按居中策略裁剪并缩放为 512×512 WebP
- **AND** 输出不包含原始 EXIF 定位或设备信息

#### Scenario：带方向信息的图片

- **WHEN** 原图包含有效方向元数据
- **THEN** 系统先应用正确方向再裁剪
- **AND** 输出像素方向与用户预览一致且元数据已清除

#### Scenario：转换失败

- **WHEN** 派生对象写入或 WebP 编码失败
- **THEN** 当前头像引用保持不变
- **AND** 临时对象进入幂等清理或重试流程

### Requirement：头像切换必须原子且失败保留旧头像

系统 SHALL 只在新派生 FileAsset 已可用、属于当前用户且资料版本匹配时原子更新 avatar 引用；旧头像只能在事务提交后异步清理。

#### Scenario：首次头像切换成功

- **WHEN** 无头像用户的新派生资产通过全部校验且资料版本匹配
- **THEN** 系统原子设置 avatar_file_asset_id 并递增资料版本
- **AND** 后续读取返回新头像

#### Scenario：更换头像成功

- **WHEN** 已有头像用户成功处理新头像
- **THEN** 系统原子切换到新资产
- **AND** 旧资产在提交后进入清理队列

#### Scenario：资料版本在处理期间变化

- **WHEN** 图片处理期间用户资料或头像已由其他请求更新
- **THEN** 切换返回 `PROFILE_VERSION_CONFLICT` 或稳定陈旧结果
- **AND** 不覆盖更新后的头像，新派生资产进入清理

### Requirement：头像删除必须恢复默认展示并安全清理

系统 SHALL 在版本匹配时原子清空头像引用并递增资料版本；前端 SHALL 使用昵称首字默认头像，旧资产由幂等任务异步清理。

#### Scenario：删除当前头像

- **WHEN** 用户携带当前资料版本删除头像
- **THEN** 系统清空引用并返回无头像状态
- **AND** 页面回到昵称首字默认头像

#### Scenario：重复删除头像

- **WHEN** 当前已经没有头像且用户重复删除
- **THEN** 系统返回幂等成功或稳定无变化结果
- **AND** 不创建重复的物理删除副作用

#### Scenario：清理任务执行前头像被重新引用

- **WHEN** 清理 worker 发现目标资产仍被任一有效资料引用
- **THEN** worker 停止物理删除并记录一致性异常
- **AND** 不依赖陈旧引用计数误删头像

### Requirement：头像必须保持私有且只允许当前用户读取

系统 SHALL 在每次头像读取时验证 active 会话、当前用户、FileAsset 所有权、`avatar` purpose 和当前资料引用；不得提供公开永久 URL 或管理员读取路径。

#### Scenario：本人读取当前头像

- **WHEN** active 普通用户请求自己当前有效头像
- **THEN** 系统返回受保护内容或短期授权读取结果
- **AND** 使用私有缓存策略且数据库不保存签名 URL

#### Scenario：跨用户读取

- **WHEN** 用户猜测其他人的 FileAsset ID 或历史头像 URL
- **THEN** 系统拒绝且不泄露资产是否存在

#### Scenario：管理员读取头像

- **WHEN** 管理员从账户列表、文件管理或直接资源路径请求普通用户头像
- **THEN** 系统拒绝读取
- **AND** 管理 API 不返回头像 URL 或 FileAsset ID

### Requirement：头像流程必须可恢复、可审计且不泄露内容

系统 SHALL 使上传完成、转换、切换、删除和清理具备幂等状态与稳定错误，并记录不含图片、对象 key、签名 URL 或原始元数据的审计。

#### Scenario：重复完成上传

- **WHEN** 客户端因网络重试重复调用同一头像 complete
- **THEN** 系统返回同一处理任务/最终状态
- **AND** 不创建多个当前头像或重复派生资产

#### Scenario：旧头像清理暂时失败

- **WHEN** 对象存储删除失败或 worker 中断
- **THEN** 新头像继续正常可用
- **AND** 清理任务按有界退避重试并保留稳定错误码

#### Scenario：审计头像操作

- **WHEN** 头像上传、转换、切换、读取或删除成功或失败
- **THEN** 审计记录操作者、目标 ID、动作、结果、request ID 和时间
- **AND** 不记录图片字节、签名 URL、对象 key、EXIF、完整文件名或解析器异常
