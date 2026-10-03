# 需求分析、设计与冻结契约

## 基线
Pen ehMic：1440×960、顶栏76、侧栏312、顶部控制125、消息流671、底部输入88；主区消息padding22/40，用户靠右灰色、AI靠左淡黄。基于该层级优化可读宽度、14px/舒适行高、紧凑图标、代码/表格内部滚动和智能跟随滚动。用户本轮需求覆盖旧设计的文字操作/语言切换/首问确认。参考豆包的立即回显、等待态、连续输出和紧凑操作，不复制品牌风格。

## 接口契约（先于并行实现）
新增POST /api/v1/learning/conversations/{conversation_id}/answers/stream，operation_id=learning_answers_stream。请求复用AnswerRequest：request_key UUID、question 1..2000、language可选nullable zh/en，省略时服务端读本人UserProfile.preferred_language：en-US->en，其他->zh。首次尝试将解析后的语言存入turn；相同key重放/重试且language省略时沿用该turn语言，不随偏好变化产生冲突。显式语言兼容原API。

响应text/event-stream，SSE每条data为AnswerStreamEvent JSON（type与其他字段组成）：
- started: {type:'started',turn:TurnView}，已持久化processing，或重放已有succeeded；
- delta: {type:'delta',delta:string}，真实上游增量正文（不暴露JSON包装/思考）；
- completed: {type:'completed',turn:TurnView}，最终校验/持久化成功，正文可替换临时文本；
- failed: {type:'failed',error_code:string,message:string}，客户端清空未校验正文并展示可重试错误，保留用户问题和request_key。
所有字段均在后端Pydantic模型定义、导出OpenAPI并生成SDK，不手写重复DTO。预响应鉴权/范围/幂等冲突必须走既有HTTP Problem；开启流后业务失败走failed终态，不用200 JSON冒充成功。Cache-Control no-store, no-transform（防Next代理gzip缓冲SSE），X-Accel-Buffering no；只一次POST、客户端禁止自动重连提交。连接断开/组件卸载取消上游并将本人租约轮次标失败；不在模型等待期间持有DB事务。原完整JSON answers端点继续支持且共用核心流水线。上游Qwen astream实际增量获取，partial正文明确为未最终校验；所有最终输出/引用校验和撤权保护保持。

## 前端消息状态
点击发送同步放入本地pending用户消息和AI loading，无论新建会话请求是否完成；输入立即清空，submitted snapshot持有问题/模式/范围/key。started事件接管该临时轮次，request_key去重；delta逐步累积，completed替换缓存，failed/断流清正文留错误和重试，同key重试不重复气泡。禁止旧轮/会话的迟到事件污染新会话。接近底部才跟随，用户阅读历史时不抢滚动，提供回到底部按钮。

## 渲染与设置
采用react-markdown+remark-gfm，支持标题、列表、引用、表格、任务列表、代码、链接；不执行任意HTML。媒体语法：Markdown图片 ![alt](url)；扩展显式安全audio/video节点（仅允许经白名单清理的audio/video/source标签及有限属性，其余HTML剥离）；另将媒体后缀链接识别为原生带controls播放器。仅安全HTTP(S)/同源相对URL，拒javascript/data/file协议；媒体不自动播放，preload=none，referrerPolicy=no-referrer用于图片，外链noopener/noreferrer，不将本应用Authorization附到外站。原生媒体不设置crossOrigin以兼容无CORS头的CDN，浏览器自身外站Cookie遵循浏览器策略；图片no-referrer，不宣称能绕过浏览器的Cookie策略。图片可键盘访问、Dialog放大/关闭，错误有可见fallback。不新增上传入口，不伪称当前模型可生成媒体资源。

个人资料现有preferred_language保持保存接口，将文案明确为默认回答语言；后台生成读取此配置，聊天中不再选择。移除学习consent读取/首次弹窗与发送门禁，不伪造consent，资料解析独立确认保持。保留有帮助/无帮助及继续追问/复制等实际操作，使用icon-only+title/aria-label，未实现生成笔记入口删除。反馈只对完成消息可用，选中可取消。

## 并行归属
backend agent：learning后端及相关测试/依赖；frontend agent：learning-page/api/queries与消息交互测试、共享lib/api/stream helper；renderer agent：answer-content及媒体组件/测试、前端包依赖、profile语言文案。主agent：AGENTS/PRD/OpenSpec、生成SDK、集成/自审/真实浏览器和清理。共享schema先确定再动工，发现契约变动先协商。

## 流中授权与参考边界

实时delta仅是暂态，已在授权时点发送的正文无法撤回；失败/撤权后客户端立即清理暂态且后端不持久化正文，后续delta需短事务复核活动用户、会话、租约和资料活动版本，不在等待模型时持事务。豆包仅只读查看了初始聊天页的输入/导航/紧凑控制，未发送消息或读取历史正文；即时/流式交互方案来自本轮明确需求，未声称实测豆包后端实现。
