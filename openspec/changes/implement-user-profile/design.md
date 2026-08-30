# Design：个人资料与默认画像

## 1. 核心决策

个人资料采用“账户身份、用户默认画像、动态诊断资产”分离模型：

```text
User
  ├─ username（只读）
  ├─ nickname（可编辑）
  └─ role / status / authentication
          │ 1:1
          ▼
UserProfile
  ├─ target_job / experience_months / target_level
  ├─ target_skills / focus_topics / learning_goal
  ├─ preferred_language
  ├─ avatar_file_asset_id
  └─ version（乐观锁）

Weakness（独立领域）
  └─ 来源、证据、严重度、掌握状态、最后验证时间
```

`UserProfile` 是用户主动维护的默认上下文，不是系统对用户的事实判定。一次业务任务可以读取它作为低优先级兜底，但不能自动回写。

## 2. 领域模型

### 2.1 `UserProfile`

- `id`、`user_id`，一对一唯一且不可改绑；
- `target_job`：可空，去除首尾空白，最大 120 字符；
- `experience_months`：可空，非负整数，首期上限 720；
- `target_level`：可空，`intern | junior | intermediate | senior | expert`；
- `target_skills`：可空数组，单项规范化、去重，最多 30 项，每项最多 50 字符；
- `focus_topics`：可空数组，最多 30 项，每项最多 80 字符；
- `learning_goal`：可空，最多 1000 字符；
- `preferred_language`：可空，首期 `zh-CN | en-US`；
- `avatar_file_asset_id`：可空，只能引用当前用户、`avatar` purpose、已处理可用的 `FileAsset`；
- `version`：从 1 递增的乐观锁版本；
- `created_at`、`updated_at`。

资料允许按需创建。首次读取尚无记录时返回字段为空、`version=0` 的稳定视图；首次更新携带 `version=0` 并原子创建，避免注册流程为所有用户强制插入空行。

工作年限展示文案由后端序列化器根据月数生成，例如 0 为“暂无工作经验”、6 为“6 个月”、24 为“2 年”、30 为“2 年 6 个月”。数据库和请求不保存第二份描述字段。

### 2.2 `User` 昵称更新

用户名不允许通过资料 API 修改。资料更新请求可以包含昵称，服务在同一事务校验并更新 `User.nickname` 与 `UserProfile`；只有昵称变化且画像尚不存在时，不强制创建空画像，但响应仍返回统一资料视图。

### 2.3 活动薄弱点投影

资料响应中的 `active_weaknesses` 来自当前用户的 `Weakness` 查询投影，只返回 ID、名称、领域、严重程度、掌握状态、来源摘要和最后验证时间。它不是 `UserProfile` 持久化字段；未实现 `Weakness` 领域或没有有效数据时返回空数组。

## 3. 头像文件模型与生命周期

### 3.1 独立用途

文件策略新增 `avatar` purpose：JPEG、PNG、WebP，默认最大 5 MB；硬上限 10 MB。上传会话由 `/api/v1/users/me/avatar-upload-sessions` 创建，不接受知识库 ID、用户 ID、bucket、object key、保留期或 purpose 的客户端覆盖。

头像使用现有 `UploadSession → StoredObject → FileAsset`，但不创建 `KnowledgeBaseFile`，也不进入解析、分块、Embedding 或检索状态机。

### 3.2 安全处理

完成上传后 worker 或受限处理器执行：

1. 复核服务端 SHA-256、对象大小和真实 MIME；
2. 使用受限图片解码器读取格式、宽高、总像素和帧数；拒绝动画、多帧、损坏、伪装、超限或解码超时；
3. 应用方向信息后清除 EXIF/ICC 等非必要元数据；
4. 以居中裁剪策略生成统一 512×512 静态 WebP；
5. 将派生 WebP 写入私有对象并创建当前用户 `avatar` FileAsset；
6. 在数据库短事务中再次校验所有权和资料版本，原子切换 `avatar_file_asset_id`；
7. 提交后把旧头像加入幂等清理队列。

原始上传对象在处理成功或失败后按临时对象策略清理。处理失败不修改现有头像；清理 worker 每次删除前重新检查是否仍被任一有效资料引用。

### 3.3 访问与删除

资料响应返回受保护的头像读取端点或短期展示 URL，不在数据库保存 URL。`GET /api/v1/users/me/avatar` 每次校验当前会话、用户状态、FileAsset 所有权和当前引用；响应使用私有缓存策略，不提供管理员读取路径。

删除头像携带当前资料版本。服务原子清空引用并递增版本，再异步清理旧资产。资料页使用昵称首字渲染默认头像，不额外创建默认图片对象。

## 4. API 边界

| 方法与路径 | 行为 |
| --- | --- |
| `GET /api/v1/users/me/profile` | 返回用户名、昵称、可选画像、年限展示文案、头像状态、资料版本和活动薄弱点 |
| `PATCH /api/v1/users/me/profile` | 携带 `version` 部分更新昵称和用户选择的画像字段 |
| `POST /api/v1/users/me/avatar-upload-sessions` | 按 `avatar` 策略创建当前用户头像上传会话 |
| `POST /api/v1/users/me/avatar-upload-sessions/{id}/complete` | 完成上传并进入头像校验/转换；重复调用幂等 |
| `GET /api/v1/users/me/avatar` | 读取当前有效私有头像；无头像返回稳定未设置状态而非文件枚举信息 |
| `DELETE /api/v1/users/me/avatar` | 携带资料版本原子清空头像并触发旧资产清理 |

所有响应复用现有 envelope、错误枚举和 RFC 9457。资料冲突返回 409 `PROFILE_VERSION_CONFLICT`；头像格式与处理失败使用稳定 `AVATAR_*` 错误，不回显对象 key、解析器异常或原始元数据。

## 5. 更新与空值语义

`PATCH` 采用字段存在性语义：省略字段表示不修改；显式 `null` 表示清空该可空画像字段；标签空数组表示清空标签。用户名即使出现在请求中也返回稳定只读字段错误。

“保存为默认画像”不属于 AgentRun 的副作用。题目、面试或计划页面只能在用户明确勾选后调用同一资料更新 API，提交当前资料版本和明确字段集合；版本冲突时停止保存默认画像，但不回滚已经合法创建的业务任务。

## 6. 前端信息架构

个人资料页包括：

- 头像上传、更换、删除、处理中和失败保留状态；
- 用户名只读、昵称可编辑；
- 目标岗位、工作年限、目标岗位等级和目标技能；
- 学习目标、重点关注知识点和默认语言；
- 有证据的活动薄弱点列表及进入对应资产的入口；
- 保存、字段错误、成功反馈和资料版本冲突恢复。

修改密码与删除账号保留独立页面或区域。页面不阻止资料未完成的用户使用其他功能，不向管理员导航增加个人画像入口。

## 7. 权限、隐私与审计

- 只有当前普通用户可读取或修改自己的资料与头像；资源 ID 查询仍需所有权校验，不能只依赖路由中的 `/me`。
- 管理员用户列表和详情继续只返回 PRD 允许的账号基本信息，不增加头像、岗位、年限、等级、技能、学习目标或薄弱点。
- 普通日志、指标和文件审计只记录用户/资料/资产 ID、动作、状态、错误码、大小和耗时，不记录画像正文、标签、头像 URL、对象 key 或图片元数据。
- 昵称和资料更新、头像创建/切换/删除及拒绝访问记录不含正文的审计事件。
- 账号软删除立即撤销头像读取和资料正常查询；头像对象进入与其他文件一致的持久化清理流程。

## 8. 验证策略

1. Pydantic 与领域单元测试覆盖字段规范化、枚举、标签去重、年限文案、空值和边界。
2. PostgreSQL 集成测试覆盖一对一约束、首次按需创建、部分更新、昵称事务和乐观锁冲突。
3. 文件集成测试覆盖 purpose 隔离、所有权、真实 MIME、解码、像素、动画、EXIF 清除、WebP 输出和失败保留旧头像。
4. 故障注入覆盖对象写入失败、转换失败、事务冲突、切换后清理失败、重复 complete/delete 和 worker 重试。
5. curl 权限矩阵覆盖本人、其他用户、管理员、未认证、禁用和软删除账号，再导出 OpenAPI 并生成前端 client。
6. Vitest 和隔离 Playwright 覆盖资料编辑、头像生命周期、默认头像、版本冲突、可选字段和独立账户安全入口。
7. 自审 API、OpenAPI、日志、审计、浏览器存储和管理员页面不存在画像或头像旁路。
