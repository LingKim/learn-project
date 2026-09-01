# processing-tasks Specification

## Requirements

### Requirement：长任务必须使用持久化通用任务事实源

系统 SHALL 使用 PostgreSQL 持久化 `BackgroundTask` 管理文档解析，不得把解析塞入 `FileCleanupTask` 或仅依赖 FastAPI 进程内后台任务。

#### Scenario：API 进程退出

- **WHEN** API 在创建处理任务后退出
- **THEN** 独立 worker 仍可从 PostgreSQL 领取任务
- **AND** 任务状态和用户可见进度不会因 API 进程退出而丢失

#### Scenario：多个 worker 竞争

- **WHEN** 多个 worker 同时轮询待处理任务
- **THEN** 任务通过 `FOR UPDATE SKIP LOCKED` 或等价机制只被一个有效租约领取
- **AND** 其他 worker 可以继续领取不同任务

### Requirement：任务必须避免长事务和陈旧提交

系统 SHALL 在短事务中领取、续租和提交状态，在事务外执行下载、解析与模型调用，并使用 lease token 与 FileAsset generation 阻止陈旧 worker 发布结果。

#### Scenario：处理超过初始租约

- **WHEN** worker 正常处理时间超过初始租约
- **THEN** worker 定期续租并保持唯一有效所有权
- **AND** 其他 worker 不得并发发布同一版本

#### Scenario：旧 worker 恢复

- **WHEN** 旧 worker 在租约失效后恢复并尝试提交
- **THEN** 系统拒绝其 lease token 或 generation
- **AND** 不覆盖新 worker 状态或活动解析版本

### Requirement：任务必须展示真实阶段和可计算进度

系统 SHALL 使用等待、下载、提取、按需 OCR、分块、Embedding、索引、发布等真实阶段；只有能够准确计数时才返回已完成单元与总单元。

#### Scenario：提取阶段总量未知

- **WHEN** 解析器尚不能准确计算完成比例
- **THEN** API 只返回当前阶段
- **AND** 前端不显示虚假百分比

#### Scenario：批量 Embedding

- **WHEN** 总分块数已知且 worker 正在生成向量
- **THEN** API 返回已处理分块数和总分块数
- **AND** 页面可显示真实计数

#### Scenario：页面级 OCR

- **WHEN** PDF 已识别出需要 OCR 的页面集合
- **THEN** API 返回已处理 OCR 页数和待 OCR 总页数
- **AND** 无待 OCR 页面时跳过 OCR 阶段，不显示虚假进度

### Requirement：取消必须在安全边界执行

系统 SHALL 允许排队任务立即取消，运行任务协作取消，并在最终发布开始后拒绝取消。

#### Scenario：取消排队任务

- **WHEN** 用户取消自己的 `pending` 解析任务
- **THEN** 任务立即进入 `cancelled`
- **AND** 原始文件保留并回到待解析

#### Scenario：取消运行任务

- **WHEN** 用户对 `processing` 任务发出取消请求
- **THEN** 任务进入 `cancel_requested`
- **AND** worker 在下一个安全检查点停止并删除本次草稿
- **AND** 已有活动版本不受影响

#### Scenario：发布阶段取消

- **WHEN** 任务已经进入不可分割的最终发布事务
- **THEN** 取消请求返回稳定冲突错误
- **AND** 不产生半发布版本

### Requirement：失败必须分类重试并保留历史

系统 SHALL 将确定性文档失败、短暂基础设施失败和配置/鉴权失败分别处理，并保留每次尝试的状态和脱敏错误码。

#### Scenario：确定性解析失败

- **WHEN** 文档损坏、OCR 后空正文、OCR 低质量、结构不支持或内容超限
- **THEN** 任务直接失败且 `retryable=false`
- **AND** 不自动重复消耗资源

#### Scenario：OCR 运行时短暂失败

- **WHEN** OCR worker 或其受控运行依赖短暂不可用或超时
- **THEN** 系统按基础设施重试策略退避重试
- **AND** 日志不包含页面图像、OCR 正文或中间文件路径

#### Scenario：Embedding 限流

- **WHEN** 千问返回可重试限流或短暂超时
- **THEN** 系统按退避策略最多自动尝试 3 次
- **AND** 日志不包含输入正文、Key 或完整响应

#### Scenario：模型鉴权失败

- **WHEN** 千问返回鉴权或永久配置错误
- **THEN** 任务直接进入最终失败并产生脱敏告警
- **AND** 不持续重试或向用户展示秘密配置

#### Scenario：用户手动重试

- **WHEN** 用户对允许重试的失败任务发起重试
- **THEN** 系统创建新任务或新尝试记录
- **AND** 历史失败记录保持可追踪且不被覆盖

### Requirement：任务权限不得暴露用户正文

系统 SHALL 只允许任务所属用户查询、取消或重试；管理员只能查看脱敏聚合指标，不能读取文件名、正文、分块、向量或模型输入。

#### Scenario：其他用户查询任务

- **WHEN** 用户请求不属于自己的任务 ID
- **THEN** 系统返回不泄露资源存在性的 404 或等价响应
- **AND** 不返回任务阶段、错误或业务对象信息
