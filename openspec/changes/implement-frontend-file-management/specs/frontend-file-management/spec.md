# frontend-file-management Specification

## Requirements

### Requirement: 内容库页面使用统一数据访问边界

前端 SHALL 通过 feature API、TanStack Query options、共享协议层和 generated SDK 调用文件管理业务接口。

#### Scenario: 页面加载知识库

- **WHEN** 已认证用户访问内容库
- **THEN** 页面通过 `file-management` query options 加载知识库分页数据
- **AND** 页面或组件不直接导入 generated SDK 或直接 `fetch` 业务接口

### Requirement: 用户可以管理知识库

前端 SHALL 支持知识库列表、创建、重命名和带影响确认的删除。

#### Scenario: 删除知识库

- **WHEN** 用户选择删除一个非最后有效知识库
- **THEN** 前端先读取删除影响与短期确认 token
- **AND** 只有用户确认删除范围后才提交删除请求
- **AND** 成功后刷新知识库列表

### Requirement: 用户可以上传支持的文件

前端 SHALL 根据后端 `UploadPlan` 执行 single 或 multipart 上传流程，并且不得自动决定重复文件处理动作。

#### Scenario: 单次上传成功

- **WHEN** 后端返回 `single` 上传计划
- **THEN** 前端把文件 PUT 到预签名 URL
- **AND** 上传成功后调用完成接口
- **AND** 文件列表显示后端返回的真实待解析状态

#### Scenario: 分片上传成功

- **WHEN** 后端返回 `multipart` 上传计划
- **THEN** 前端按 `part_size` 切片并按需请求分片签名
- **AND** 收集每个响应 ETag 后提交完成接口

#### Scenario: 返回重复文件处理状态

- **WHEN** 后端返回 `reuse` 或 `DUPLICATE_ACTION_REQUIRED`
- **THEN** 前端停止自动上传并展示明确错误
- **AND** 不自动替用户选择关联、移动或取消

### Requirement: 用户可以管理知识库文件

前端 SHALL 支持文件分页、搜索、状态筛选、重命名、移动、下载和带影响确认的删除。

#### Scenario: 移动文件

- **WHEN** 用户选择另一个知识库并确认移动
- **THEN** 前端调用真实移动接口
- **AND** 成功后刷新来源和目标知识库相关查询

#### Scenario: 下载文件

- **WHEN** 用户点击下载
- **THEN** 前端请求短期下载 URL
- **AND** 不持久化、不记录、不在页面展示该 URL

### Requirement: 页面不得伪造尚未实现的后端能力

前端 SHALL 只暴露当前 OpenAPI 可调用的操作。

#### Scenario: 设计稿含有重新解析和恢复操作

- **WHEN** Pencil 示例出现重新解析、取消解析、恢复或永久清理
- **THEN** 本次实现不渲染这些操作
- **AND** 不用 mock 成功或禁用假按钮冒充已接入能力

### Requirement: 文件管理具备真实自动化验收

前端 SHALL 通过单元测试和隔离 Playwright E2E 验证核心闭环。

#### Scenario: E2E 文件 CRUD

- **WHEN** 测试环境 PostgreSQL、Redis 与 RustFS 可用
- **THEN** E2E 在隔离数据库/前缀中完成认证、知识库 CRUD、TXT 上传和文件重命名、移动、下载请求、删除
- **AND** 测试结束后执行清理并报告结果
