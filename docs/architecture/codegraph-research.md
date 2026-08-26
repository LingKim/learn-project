# CodeGraph 工具调研

> 调研日期：2026-08-26
>
> 调研对象：`npx @colbymchenry/codegraph`，核对版本为 npm `latest` 的 `1.5.0`。
>
> 证据边界：仅使用 npm Registry 包元数据、官方 GitHub 仓库 README/源码、官方 Release 与提交记录；未安装、未执行该包。

## 结论

CodeGraph 是一个给 AI 编码工具使用的**本地代码知识图谱与 MCP 服务**。它用 tree-sitter 和静态分析抽取函数、类、方法、调用、导入、继承、实现及部分框架路由关系，保存到项目内的 SQLite 数据库，再向 Codex、Claude Code、Cursor 等工具提供源码探索、调用链和影响范围查询。[3][9]

对于当前 Next.js + FastAPI 项目，它有一定价值，但**现在不建议直接裸跑未锁版本的 `npx @colbymchenry/codegraph`**：

1. 当前 `frontend/src` 与 `backend/src` 合计 86 个文件、约 616 KB，代码量尚不大；`rg`、类型检查、测试和现有架构文档仍足以完成多数定位工作，预建图谱的边际收益有限。
2. TypeScript/TSX、JavaScript 和 Python 都是官方标注的完整支持语言；FastAPI 路由也被明确支持，因此随着项目增长，跨前后端检索、调用链和变更影响分析会更有价值。[3]
3. 官方框架路由清单没有列出 Next.js。它仍能分析 `.ts`/`.tsx` 的符号、导入和调用关系，但不能据此假定它理解 Next.js App Router、Server Actions、Route Handlers 等全部约定。[3]
4. 裸 `npx` 会下载并执行第三方发布物，然后进入一个会改写 AI 工具配置的交互式安装器；默认选项还可能全局安装 CLI。它不是无副作用的“查看帮助”命令。[4][5][6]

建议等到项目模块和调用链明显增多，或实际出现“每次都要大量 grep/read 才能梳理链路”的痛点，再做一个可回滚试用。试用时应锁定版本、关闭遥测、先审阅将要写入的 MCP 配置，并把 `.codegraph/` 保持为本地生成物。

## 它解决什么问题

普通文本搜索只能找到字面匹配；CodeGraph 预先构建以下关系，供 CLI 或 MCP 查询：[3]

- 代码节点：文件、函数、方法、类、接口、变量、路由等；
- 代码边：调用、导入、引用、继承、实现和部分动态分派关系；
- 查询结果：相关源码、调用者/被调用者、符号间路径、变更影响半径、可能受影响测试；
- 持久化：项目内 `.codegraph/codegraph.db`，使用 SQLite FTS5；
- 同步：初始化后由 MCP 服务监听文件变化并增量更新索引。

核心 MCP 工具是 `codegraph_explore`。官方将其定位为一次返回相关源码、关系路径和 blast radius 的综合查询；其他 `node`、`search`、`callers`、`callees`、`impact`、`files`、`status` 工具仍存在，但默认不全部暴露在 MCP 工具列表中。[3]

需要注意，README 中“减少多少 token / tool call”以及各语言覆盖率都是项目作者自己的 benchmark，不是独立第三方验证。它们可以说明设计目标，不能当作对当前仓库的确定收益。[3]

## `npx` 到底会做什么

### 裸命令：`npx @colbymchenry/codegraph`

执行链路如下：

1. `npx` 从 npm 获取当前 `latest`，并把发布物放入 npm 的本地缓存后执行。本次核对时为 `1.5.0`；不写版本意味着以后可能执行不同代码。[1]
2. npm 主包的 `bin` 是 `codegraph -> npm-shim.js`。主包把六个平台包列为 `optionalDependencies`，npm 会选择当前 OS/CPU 对应的一个包。[1][6]
3. `npm-shim.js` 使用当前机器的 Node 作为启动器，再执行平台包内自带 Node 运行时和 CodeGraph CLI。[6]
4. 如果 npm 镜像没有同步平台包，shim 会从官方 GitHub Release 下载对应压缩包，解压并缓存到 `~/.codegraph/bundles/<平台>-<版本>/`。可以用 `CODEGRAPH_NO_DOWNLOAD=1` 禁止这条 fallback。其校验是 best effort：能取得 `SHA256SUMS` 时不匹配会中止，但校验文件缺失或不可达时仍会继续执行 HTTPS 下载的归档。[6]
5. CLI 发现没有任何参数时调用 `runInstaller()`，即进入交互式安装器，而不是索引当前目录或打印帮助。[4]

### 安装器可能产生的变更

交互式安装器会按选择执行以下动作：[5]

- 检测并选择 Claude Code、Cursor、Codex CLI、opencode、Hermes Agent、Gemini CLI、Antigravity、Kiro；
- 默认询问是否执行 `npm install -g @colbymchenry/codegraph`，初始选项为“是”；
- 选择全局或项目级配置位置；
- 写入所选代理的 MCP server 配置和少量使用指引；
- Claude Code 还会询问命令自动放行和 prompt hook，初始选项为“是”；
- 询问是否开启匿名遥测，初始选项为“是”；
- 可选询问是否提交邮箱加入产品 beta，只有明确同意并输入邮箱才会发送。

以 Codex v1.5.0 的全局安装为例，源码会修改 `~/.codex/config.toml`，加入 `[mcp_servers.codegraph]`，并在 `~/.codex/AGENTS.md` 插入带标记的 CodeGraph 指引块。[10]

安装器**不会自动索引当前仓库**。官方源码特意把索引留给用户后续显式执行 `codegraph init`，避免意外扫描当前 shell 所在目录。[5]

### 带参数运行

`npx` 会把后续参数传给同一 CLI。例如：

```bash
# 仅打印 Codex MCP 配置，不写文件
npx @colbymchenry/codegraph@1.5.0 install --print-config codex

# 显式初始化并索引当前项目，会写 .codegraph/
DO_NOT_TRACK=1 npx @colbymchenry/codegraph@1.5.0 init
```

第二条只是说明 CLI 语义，本次调研没有执行。若目的是“先看看”，第一条比裸命令更可控，但 `npx` 仍会下载并执行 npm 发布物。[4]

## 支持的语言与框架

### 语言

v1.5.0 README 标注完整支持：[3]

- Web/脚本：TypeScript、JavaScript、ArkTS、Python、PHP、Ruby、Lua、Luau、R；
- 系统/移动：Go、Rust、C、C++、C#、Swift、Kotlin、Scala、Dart、Metal、CUDA；
- 前端单文件/模板：Svelte、Vue、Astro、Liquid；
- 其他：Java、Pascal/Delphi、CFML、COBOL、Visual Basic .NET、Erlang、Solidity、Terraform/OpenTofu、Nix。

Objective-C 被标为部分支持。语言支持依据文件扩展名自动选择；大于 1 MB 的文件，以及 `node_modules`、`.next`、`dist`、`.venv` 等依赖、构建和缓存目录默认跳过，同时遵守 `.gitignore`。[3]

### 框架与路由

官方列出的框架路由识别包括：[3]

- Python：FastAPI、Flask、Django；
- Node/TypeScript：Express、NestJS、React Router；
- Java/Kotlin/Scala：Spring、Play；
- PHP：Laravel、Drupal；
- Ruby：Rails；
- Go：Gin、chi、gorilla/mux；
- Rust：Axum、actix、Rocket；
- Swift：Vapor；
- 文件路由：SvelteKit、Vue/Nuxt、Astro。

官方自测称 FastAPI 框架路由覆盖率为 98%，但没有列 Next.js。因此当前后端契合度高，前端只有语言级和一般 React/TypeScript 关系分析可以确认，不能把 React Router 支持等同于 Next.js 支持。[3]

## 输出、依赖和典型用法

### 输出与本地文件

- `codegraph init` 创建 `.codegraph/`，其中主要是 `codegraph.db`、WAL/SHM、守护进程状态、日志等；工具会写 `.codegraph/.gitignore`，默认忽略该目录内除 `.gitignore` 外的所有文件。[3][9]
- 索引是 SQLite 知识图谱，并非生成业务源码或替换项目构建产物。
- CLI 可输出人类可读文本，部分查询支持 `--json`；MCP 返回相关源码、符号关系和影响分析上下文。[3]
- 可选 `codegraph.json` 用于自定义扩展名，以及 `include`、`exclude` 等索引规则。[3]

### 运行依赖

- npm 发布采用“薄主包 + 当前平台可选包”；平台包包含编译后的程序、Rust 内核、语法资源和自带 Node 运行时。[1][6][7]
- v1.5.0 GitHub Release 的平台压缩包约 48–62 MB；当前项目所在的 macOS arm64 对应 npm 平台包约 57.6 MB 压缩、288.9 MB 解包，索引数据库还会继续占用本地磁盘。[8][14]
- CLI/MCP 使用内置运行时；作为 JS/TS 库嵌入自己的进程时，官方要求宿主 Node 22.5+ 才能使用 `node:sqlite`。[3]

### 常用命令

```bash
codegraph install                 # 配置 AI 工具的 MCP 接入
codegraph init [path]             # 创建索引并完成第一次全量构建
codegraph status [path]           # 查看索引状态
codegraph sync [path]             # 手动增量同步
codegraph explore "认证流程"     # 综合返回源码、调用路径和影响摘要
codegraph query "UserService"    # 搜索符号
codegraph callers <symbol>        # 查调用者
codegraph callees <symbol>        # 查被调用者
codegraph impact <symbol>         # 查变更影响范围
codegraph affected [files]        # 查可能受影响的测试
codegraph uninit [path]           # 删除该项目的 .codegraph/
codegraph uninstall               # 移除代理配置和 CLI，不删除项目索引
```

## 隐私与联网边界

### 源代码是否上传

根据官方 README 和遥测规范，源码、路径、文件名、仓库名、符号名、搜索查询都不发送，索引保存在本地 SQLite。[3][11]

但“100% local”不能理解成“完全不联网”：

- npm/npx 安装本身访问 npm Registry；缺少平台包时还可能访问 GitHub Release。[6]
- 匿名遥测默认选项为开启，发送随机 machine ID、版本、OS/架构、Node 主版本、所用命令/工具、语言名、文件数和耗时区间等聚合数据；官方称不发送代码、路径和查询。[11]
- 遥测发往 `telemetry.getcodegraph.com`，再转发到 PostHog 美国区域。[11]
- MCP 服务每天最多一次查询 GitHub 最新版本；`CODEGRAPH_NO_UPDATE_CHECK=1` 可单独关闭，`DO_NOT_TRACK=1` 会同时关闭遥测和更新检查。[11]
- beta 邮箱提交是独立、明确选择后的联网行为。[5]
- CodeGraph MCP 会把命中的源码片段交给所接入的 AI Agent；这些内容之后是否发送到模型服务，取决于 Codex/Claude/Cursor 及其模型的数据策略，不属于 CodeGraph 本地索引承诺能控制的范围。[3]

因此更准确的结论是：**代码索引本地化，但默认存在非代码遥测和更新检查网络流量。**

## 维护状态、许可证与风险

### 维护状态

- npm 包创建于 2026-01-18；截至 2026-07-21 已发布 45 个版本，`latest` 为 `1.5.0`。[1]
- v1.5.0 由 GitHub Actions 发布，npm 元数据带 trusted publisher 和 SLSA provenance attestation；官方 Release 同日提供多平台构建与校验值。[1][8]
- 官方仓库在 2026-08-22 仍有功能、性能和兼容性提交，说明仍在积极维护。[12]
- 仓库和 npm 包均使用 MIT License。[1][13]

### 潜在风险

1. **供应链执行风险**：`npx` 会直接执行 npm 当前 `latest`，且程序还能在平台包缺失时下载 GitHub 二进制；fallback 在无法取得 `SHA256SUMS` 时仍会继续。锁定版本只能降低漂移，不能消除第三方代码执行风险。[1][6]
2. **配置写入范围较大**：裸命令是安装器，可能全局安装 CLI，并修改 Codex/Claude/Cursor 等配置或指引文件；默认选择偏向启用。[5][10]
3. **资源占用**：平台包体积较大；大仓库的全量解析、SQLite 数据库、WAL 和后台文件监听会使用 CPU、内存与磁盘。[3][8]
4. **静态分析边界**：反射、动态导入、运行时依赖注入、框架隐式约定可能漏边或误判。影响分析只能作为导航线索，不能替代测试。[3]
5. **项目较新且发布节奏快**：版本迭代积极，也意味着行为、索引格式和安装方式变化较快。当前 `main` 已包含晚于 v1.5.0 的提交，审计时应以实际安装的 tag/发布物为准。[8][12]
6. **隐私表述易被误读**：源码不上传不等于零网络；默认遥测、更新检查和可选 beta 邮箱需要按项目隐私要求分别处理。[5][11]

## 对学面通AI的建议

### 当前价值判断

| 场景 | 价值 | 判断依据 |
| --- | --- | --- |
| FastAPI 路由到 service/repository 的调用链 | 中到高 | Python 和 FastAPI 明确支持，适合梳理跨模块调用和影响范围。 |
| Next.js/React/TypeScript 组件与普通函数关系 | 中 | TS/TSX 完整支持，可追踪导入和调用；React 动态分派也有专项处理。 |
| Next.js App Router/Server Actions/Route Handlers 语义 | 不确定 | 官方路由框架清单未列 Next.js，不能预设支持。 |
| 前后端 HTTP 契约链路 | 低到中 | 两端语言都可索引，但静态图未必能把 OpenAPI 生成客户端与 FastAPI handler 自动连成完整跨语言业务链。 |
| 当前小规模仓库日常定位 | 低到中 | 现有 `rg`、类型系统、测试和架构文档成本更低，没有证据表明当前已出现搜索瓶颈。 |
| 后续模块增多后的重构/影响分析 | 中到高 | 这是预建调用图和 blast radius 最契合的场景，但仍需自动化测试确认。 |

### 若要试用

建议不要直接执行裸命令，而是按以下控制点进行：

1. 先锁定已审阅版本，例如 `@1.5.0`，不要依赖可漂移的 `latest`。
2. 先用 `install --print-config codex` 查看 MCP 配置，再决定是否允许写入。
3. 设置 `DO_NOT_TRACK=1`；如只关闭更新检查，另用 `CODEGRAPH_NO_UPDATE_CHECK=1`。
4. 避免安装器默认的全局写入，明确选择所需代理和配置范围。
5. 初始化前确认 `.gitignore` 与 `codegraph.json` 排除了大体积资料、上传文件、生成客户端、密钥文件和其他不应解析的本地内容。
6. 用 2–3 条真实问题对比现有工具：认证链路、FastAPI 路由影响范围、前端生成 SDK 调用入口。只有在答案更完整且工具调用明显减少时再保留。
7. 即使启用，也把它定位为只读导航和影响分析辅助；项目真实边界仍以源码、OpenAPI、OpenSpec 和自动化测试为准。

## 第一方资料

1. [npm Registry：`@colbymchenry/codegraph@1.5.0` 元数据](https://registry.npmjs.org/@colbymchenry/codegraph/1.5.0)
2. [npm 包页面：`@colbymchenry/codegraph`](https://www.npmjs.com/package/@colbymchenry/codegraph)
3. [官方 README：v1.5.0](https://github.com/colbymchenry/codegraph/blob/v1.5.0/README.md)
4. [官方 CLI 入口源码：无参数进入安装器](https://github.com/colbymchenry/codegraph/blob/v1.5.0/src/bin/codegraph.ts#L123-L132)
5. [官方安装器源码：交互项、配置写入与不自动索引](https://github.com/colbymchenry/codegraph/blob/v1.5.0/src/installer/index.ts#L81-L300)
6. [官方 npm shim：平台包选择、执行与 GitHub fallback](https://github.com/colbymchenry/codegraph/blob/v1.5.0/scripts/npm-shim.js)
7. [官方 npm 打包脚本：薄主包与平台可选包](https://github.com/colbymchenry/codegraph/blob/v1.5.0/scripts/pack-npm.sh)
8. [官方 GitHub Release：v1.5.0](https://github.com/colbymchenry/codegraph/releases/tag/v1.5.0)
9. [官方目录源码：`.codegraph/` 与内部 `.gitignore`](https://github.com/colbymchenry/codegraph/blob/v1.5.0/src/directory.ts#L586-L660)
10. [官方 Codex 安装目标源码：写入位置和内容](https://github.com/colbymchenry/codegraph/blob/v1.5.0/src/installer/targets/codex.ts)
11. [官方遥测规范：收集字段、禁用方式与传输目的地](https://github.com/colbymchenry/codegraph/blob/v1.5.0/TELEMETRY.md)
12. [官方仓库提交记录](https://github.com/colbymchenry/codegraph/commits/main/)
13. [官方 MIT License](https://github.com/colbymchenry/codegraph/blob/v1.5.0/LICENSE)
14. [npm 平台包：`@colbymchenry/codegraph-darwin-arm64@1.5.0`](https://www.npmjs.com/package/@colbymchenry/codegraph-darwin-arm64/v/1.5.0)
