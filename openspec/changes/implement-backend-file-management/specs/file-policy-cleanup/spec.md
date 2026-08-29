# File Policy and Cleanup Specification

## Requirement：文件策略必须版本化发布

系统 SHALL 保存草稿和不可变已发布文件策略。已认证用户可以读取当前有效规则；只有管理员可以创建、修改草稿和发布。发布 SHALL 使用基准版本防止并发覆盖。

### Scenario：发布有效草稿

- **WHEN** 管理员发布满足硬上限且基准版本仍为当前版本的草稿
- **THEN** 系统原子激活新版本并冻结其内容
- **AND** 只影响之后创建的上传会话

### Scenario：并发发布冲突

- **WHEN** 管理员基于已经过期的当前版本发布草稿
- **THEN** 系统返回 409 `FILE_POLICY_VERSION_CONFLICT`
- **AND** 不覆盖已发布的新版本

### Scenario：普通用户修改策略

- **WHEN** 普通用户调用策略创建、修改或发布接口
- **THEN** 系统返回 403
- **AND** 不产生策略版本或审计副作用

## Requirement：文件清理任务必须持久化且幂等

对象验证、补偿和删除 SHALL 由 PostgreSQL 持久化任务驱动。FastAPI 进程内临时后台任务 SHALL NOT 成为唯一执行机制。多个 worker SHALL 安全竞争任务且同一任务最多有一个有效租约。

### Scenario：worker 处理中重启

- **WHEN** worker 领取任务后在提交结果前退出且租约到期
- **THEN** 其他 worker 可以重新领取同一任务
- **AND** 幂等执行不得创建重复关联、重复引用或误删对象

### Scenario：对象已经不存在

- **WHEN** 物理删除任务请求删除已经不存在的目标对象
- **THEN** 任务视为幂等成功并记录 cleared_at
- **AND** 不无限重试或恢复已删除业务记录

## Requirement：重试必须区分确定性与暂时性失败

确定性文件验证失败 SHALL NOT 自动重试。短暂 RustFS/数据库故障 SHALL 最多自动重试 3 次；物理删除 SHALL 最多重试 8 次并逐步延长间隔。超过上限 SHALL 进入最终失败和脱敏告警。

### Scenario：格式确定无效

- **WHEN** 校验器确认文件类型或结构不符合策略
- **THEN** 任务直接进入最终拒绝状态
- **AND** 只对临时对象清理进行必要重试

### Scenario：RustFS 暂时不可用

- **WHEN** 对象读取或删除返回可重试的存储故障
- **THEN** 任务按对应上限安排下一次执行
- **AND** 用户业务响应不得伪报物理清理已完成

## Requirement：物理删除必须复核真实引用

系统 SHALL 将有效 FileAsset 引用作为删除 StoredObject 的事实源。引用计数仅为性能字段；删除前 SHALL 锁定对象并复核有效引用。计数不一致时 SHALL 停止删除并创建一致性修复任务。

### Scenario：删除最后一个引用

- **WHEN** 锁内查询确认 StoredObject 已无任何有效 FileAsset
- **THEN** 系统将对象标记为 DELETING 并创建唯一物理删除任务
- **AND** 删除成功后记录 cleared_at

### Scenario：引用计数漂移

- **WHEN** StoredObject.reference_count 与有效 FileAsset 数量不同
- **THEN** 系统停止本次物理删除
- **AND** 生成修复任务且不影响仍有效用户访问

## Requirement：Scheduler 必须单例调度且可恢复

独立 scheduler SHALL 使用 PostgreSQL advisory lock 或等价数据库锁保证多实例下单一有效调度。每天 02:30 Asia/Shanghai SHALL 生成到期录音、过期上传、临时对象和失败清理任务。

### Scenario：两个 scheduler 同时启动

- **WHEN** 两个实例同时到达调度时间
- **THEN** 最多一个实例获得锁并生成本轮任务
- **AND** 任务幂等键继续防止重复副作用

### Scenario：调度实例错过执行时间

- **WHEN** scheduler 在计划时间不可用后重新启动
- **THEN** 系统可以补生成尚未执行的到期任务
- **AND** 不依赖进程内定时器历史恢复状态

## Requirement：孤儿对账必须采用保护期

系统 SHALL 每周日 03:30 Asia/Shanghai 分页核对 PostgreSQL 与 RustFS。没有数据库引用的对象 SHALL 在连续两次确认且首次发现至少 7 天后才允许删除；数据库记录存在但对象缺失 SHALL 被标记不可用并告警。

### Scenario：首次发现未知对象

- **WHEN** 对账在 bucket 中发现数据库没有有效记录的对象
- **THEN** 系统只创建或更新孤儿候选
- **AND** 本轮不得直接删除对象

### Scenario：数据库对象缺失

- **WHEN** 有效 FileAsset 引用的 StoredObject 在 RustFS 中不存在
- **THEN** 系统将相关文件标记不可用并产生脱敏告警
- **AND** 不创建伪对象或返回可下载状态

## Requirement：用户文件清理能力必须可独立调用

系统 SHALL 提供可执行、可测试的 `enqueue_user_file_cleanup(user_id)` 应用用例，供未来账号删除编排调用。该用例 SHALL 立即撤销用户全部文件访问并为知识库关联、逻辑资产和临时上传生成幂等清理任务。

### Scenario：清理用户文件

- **WHEN** 账号删除业务编排调用用户文件清理能力
- **THEN** 该用户无法再列出、下载、移动或续签任何文件和上传会话
- **AND** 共享物理对象只在其他有效引用也消失后删除

### Scenario：重复调用用户清理

- **WHEN** 同一用户清理能力因事务或消息重试被重复调用
- **THEN** 系统返回同一收敛结果
- **AND** 不产生重复物理删除或影响其他用户

## Requirement：文件审计必须脱敏并按期保留

系统 SHALL 审计创建上传、完成、关联、下载授权、移动、重命名、删除和物理清理，但 SHALL NOT 记录文件名、正文、摘要、预签名 URL、bucket 或 object key。普通技术记录 SHALL 按已确认期限清理。

### Scenario：生成下载地址

- **WHEN** 用户成功请求文件下载地址
- **THEN** 审计只记录操作者、动作、业务目标 ID、结果、request ID、IP 哈希和时间
- **AND** 日志与审计均不包含签名 URL 或原始文件名

### Scenario：技术记录到期

- **WHEN** 成功上传会话或成功清理记录超过 90 天，或最终失败任务/文件审计超过 180 天
- **THEN** 保留任务可以物理删除对应技术元数据
- **AND** 不删除仍有效的文件资产、业务关联或策略历史版本
