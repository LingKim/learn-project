# Tasks: 内容库前端与文件管理联调

## 1. 规格与现状

- [x] 核对 Git 提交记录和未提交文件后端改动
- [x] 读取 Pencil 35–37 页面及真实后端 OpenAPI 契约
- [x] 明确设计稿中解析/恢复能力不在本次范围

## 2. 前端数据层

- [x] 实现 `features/file-management/api.ts`，覆盖知识库、上传会话和文件接口
- [x] 实现分层 query key、query options 和 mutation options
- [x] 实现单次与 multipart 预签名上传传输层及失败取消
- [x] 增加 API、Query 和上传单元测试

## 3. 页面与交互

- [x] 实现内容库共享应用框架和根首页入口
- [x] 实现知识库总览、创建、重命名和删除影响确认
- [x] 实现知识库详情、搜索/筛选/分页与文件表格
- [x] 实现文件上传、重命名、移动、下载和删除影响确认
- [x] 对齐 Pencil 视觉并补齐响应式、加载、错误和空状态

## 4. 联调与 E2E

- [x] 新增隔离文件管理 E2E runner，不管理宿主 PostgreSQL/Redis 生命周期
- [x] 使用真实后端、RustFS 和浏览器完成知识库与文件 CRUD 闭环
- [x] 验证临时数据、上传会话和测试服务清理

## 5. 自审与交付

- [x] 运行 format、lint/boundaries、typecheck、Vitest 和 OpenAPI check
- [x] 更新 evidence 与任务状态，记录真实结果和未验证项
- [x] 用户已完成本地页面验收，并于本轮明确授权 commit、push
