# Evidence：认证入口前端页面

> 说明：本文件主体记录 2026-08-24 的历史实施证据。2026-08-25 已取消首次登录强制改密，并在 `implement-authentication` 变更中完成旧页面删除、真实认证联调和 Playwright E2E；当前结果以该变更的 evidence 为准。

## 设计与需求核对

- 通过 Pen 桌面文件逐张查看 `01·认证·登录·默认`、`02·认证·注册·默认`、`03·认证·首次登录改密·强制`。
- 保留左右分栏、象牙白/浅沙色/暖黄和小圆角视觉。
- 按 PRD 修正 Pen 冲突：手机号或邮箱改为用户名；移除忘记密码、用户协议和手机号/邮箱验证码相关内容。
- 认证业务组件不再直接创建输入框或复选框，统一组合 `InputField`、`PasswordField`、`CheckboxField` 和既有 `Button` 公共组件。
- shadcn CLI `latest` 与 `4.18.0` 两次请求 registry 时均被远端关闭；随后只读核验相同官方 registry URL 返回 200，并按返回的 `new-york-v4` 源码落入 `Input`、`Checkbox`、`Label`，同时安装其声明的 `radix-ui` 依赖。未把此前手写复刻版冒充为官方组件。

## 自动化验证

工作目录：`frontend/`

```text
pnpm lint
结果：通过，0 warnings

pnpm typecheck
结果：通过

pnpm test
结果：通过，2 个测试文件、6 个测试
```

按项目规则未运行 `next build` 或 Docker build。

## 本地浏览器验证

- Next.js dev server：`http://localhost:3000`
- 已访问并读取 `/login`、`/register`、`/first-login/change-password` 的真实页面语义树。
- 登录表单填入非敏感测试值后，真实水合提交显示“前端校验已通过，认证接口尚未接入。”
- 390 × 844 移动端视口检查：页面宽度 390、文档滚动宽度 390，无横向溢出；强制改密页可纵向滚动查看完整表单。
- ego-browser 的 `Page.captureScreenshot` 两次超时，因此本轮没有把浏览器截图列为验收证据；视觉基线来自 Pen 只读截图，运行页以 DOM、可访问树和布局尺寸完成核验。

## 未验证与后续边界

- 当前 OpenAPI 只有健康检查接口，没有认证请求/响应、会话和强制改密标记契约。
- 未验证真实注册、登录、Cookie/Token、失败限流、账号锁定和改密后旧会话失效；这些必须在后端认证 OpenAPI 完成后联调。

以上两项是 2026-08-24 的历史未验证状态，已由 2026-08-25 的 `implement-authentication/evidence.md` 完成并取代；首次强制改密相关验收已取消。
