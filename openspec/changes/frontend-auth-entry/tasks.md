# Tasks：认证入口前端页面

- [x] 核对 Pen、PRD 和当前 OpenAPI，记录冲突与集成边界
- [x] 新增认证页面公共壳和三个 App Router 路由
- [x] 实现登录、注册、强制改密表单及可访问校验
- [x] 将输入框、复选框和密码字段收敛为 `src/components/ui` 公共组件
- [x] 用 shadcn 官方 registry 的 `Input`、`Checkbox`、`Label` 替换基础控件复刻版
- [x] 增加认证页面组件测试
- [x] 执行 Oxfmt、Oxlint、TypeScript 和 Vitest 非 build 验证
- [ ] 后端认证 OpenAPI 就绪后接入真实提交、会话和强制改密路由守卫
