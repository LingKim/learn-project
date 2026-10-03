# 验证记录（2026-10-03）

## 自动化与契约

前端 TypeScript、Oxlint/API边界、Oxfmt、OpenAPI生成一致性通过；Vitest 20文件84项通过，新增5项真实QueryClient设置行为测试（默认值、带版本保存和缓存更新、失败不改变布局、409刷新重试、取消）。后端相关pytest 33项通过，Ruff与修改文件mypy通过。无build，无Git commit/push/PR。

## 运行与数据库

核对.env目标localhost/xuemian_ai、读回current=20261002_02。创建权限700目录/600自定义pg_dump备份，pg_restore -l验证可读取且包含user_profiles；备份/private/tmp/xuemian-navigation-backup-20261003-101943/xuemian_ai.dump（137051字节）。迁移仅20261003_01，读回版本与现有profile默认left；没有启停外部PostgreSQL/Redis。按原参数重启本项目API（无自动重载），运行OpenAPI返回新字段并读取profile/会话成功。备份未执行真实恢复演练。

## 浏览器与Pen

ego-browser独立任务空间，已认证的现有验收账号：左侧rail宽64px，历史top=0、高828px等于窗口828px；原顶栏76px空间释放。顶部保存后height=56px、历史top=56px，刷新恢复top；切回left时草稿文本不变，随后清空验证草稿。内容库hover显示tooltip，rail无横向滚动。375/768/1024/1440宽度页面无横向溢出。真实历史会话、用户设置Dialog截图经视觉查看；Pen三稿结构与截图核验，后续独立读取无裁切问题。最终账号偏好恢复left。

实现支持账号跨设备同步，实际验证了数据库持久化和刷新读取；未在第二台物理设备验收。小屏使用紧凑可横向滚动图标导航；项目只有当前浅色主题，本次未添加暗色主题。人工验收待用户完成。
