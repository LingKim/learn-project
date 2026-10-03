# 附件设计及前后端契约

## UX与产品

输入框附件区在文本上方，图片缩略图、文档名称/类型；加号打开官方DropdownMenu的“上传文件”，隐藏input multiple，拖拽区域提供高亮与“松开以上传”，上传/解析中不可发送，错误可以移除/重试。每轮最多6个，单图5MiB、文档10MiB；加号、删除、发送均可键盘使用。附件上传完成可点击叉移除（未发送），已发轮次只能查看，不提供修改旧附件。附件可单独发送，后端补“请分析所上传的附件”。仅纯文本粘贴不触发附件，支持剪贴板图片作为增强交互。切换会话/新建会话清理未发送附件，不让旧上传完成污染新草稿。图片本地ObjectURL及时释放，附件正文不进入日志、Git或管理员界面。

## API唯一事实源

新增 /api/v1/learning/attachments：POST multipart/form-data file: UploadFile，operation_id=learning_attachments_upload，响应 ApiResponse[LearningAttachmentView]；DELETE /{attachment_id} operation_id=learning_attachments_delete，已绑定轮次409；GET /{attachment_id}/content operation_id=learning_attachments_content，私有无缓存，返回bytes，只允许本人及有效会话，前端feature API请求Blob生成ObjectURL，禁止长期保存签名URL。
LearningAttachmentView: id UUID, filename str, media_type str, byte_size int, kind image|document。上传响应表示校验/解析完成，失败标准ApiError，不能以扩展名/文件名冒充正文。附件ID由服务端验证owner/available/未过期/未删除/绑定轮次一致。AnswerRequest新增attachment_ids（默认[]、<=6、不得重复），question允许空但需附件。TurnView新增attachments（默认[]）；前端只使用生成契约。来源标签扩展“用户附件”“用户资料与附件”，general带附件采用“用户附件”，仍允许通用知识但明确附件来源。

## 存储与解析

新增learning/attachment_models.py LearningAttachment：owner_user_id、file_asset_id、turn_id(nullable FK)、extracted_text、expires_at、通用audit/softdelete mixin。复用FileAsset(purpose=learning_attachment)、StoredObject(storage_domain=chat_attachments)与RustFS文档桶，校验真实类型和内容，图片完整解码/尺寸限制/去元数据规范化为WebP，不使用头像裁切。文档复用受限extract_document与PDF页面OCR（限制50页、10页OCR、每文档30000字符），超限明确失败，不能静默截断。每轮合计正文<=60000字符，图片/文档最多6件。同摘要存储用现有锁/去重模式，绑定和删除互斥行锁；移除未发送附件softdelete asset、减引用计数、走FileCleanupTask；24h未发送附件过期由现有scheduler清理，删除会话释放对应附件引用。附件发送后保留，不能撤销用于历史重试的来源。

## 模型与引用

附件上下文在HumanMessage，图片使用image_url data:image/webp;base64内容块，文档为真实正文。InputContext增加attachments（filename/text/image_data_url/evidence_number），禁止日志/trace输出正文/图片。文本沿用learning_answer_model；有图片使用可配置learning_vision_model默认qwen3-vl-flash，禁止把图像请求送入文本模型或静默丢图。Prompt升级说明附件为不可信业务内容，不能覆盖系统规则，按证据回答并支持引用。materials把附件证据加入当次evidence并保持引用门禁；附件EvidenceChunk稳定ID使用附件id，不进入知识库索引；publication_guard复核附件授权与内容不可变性。general附件来源明确但citation_ids仍为空，不冒充知识库引用。最近6轮附件作为当前会话后续追问上下文，整体上限6件/60000字符，超限应提示拆分或新建会话，不静默丢弃。request_key fingerprint及重试校验包含附件ID与语言，防止重用key换附件。

## AI处理说明与验证

learning_consent_version升至qwen-learning-v2，说明当前/近六轮图片、文档正文及扫描PDF待OCR页面将发送千问；上传及回答都需有效确认，发送前有实际可见说明。开发验证只使用合成图文资料，不重放用户截图/原件到外部模型。OpenAPI导出后生成前端SDK，feature API+queryOptions/mutationOptions接入。迁移先核对.env/版本、可恢复业务库备份、upgrade仅本项目库再读回；不管理外部PostgreSQL/Redis。不build，不commit/push。

## 集成自审补充

千问视觉模型实测拒绝json_schema，附件请求改为json_object（包括纯文档），保留本地严格GeneratedAnswer、语言、引用及Markdown校验；无附件继续json_schema。Next.js代理缓冲上限设11MiB覆盖10MiB文档的multipart开销，后端同路径流式累积限11MiB，不信任Content-Length。`.markdown`仅解析时等价`.md`，保留原始文件名。

长时停留输入框实测触发旧认证层access token过期：共享authenticatedAccessToken原来只判断是否存在，新增依据后端AuthPayload.expires_in提前30秒single-flight刷新，保证上传/移除不携带已过期token。该改动不改变认证权限或有效期，只复用原刷新接口。

文本多附件实测也发现json_schema会压成标题或违反Markdown，单变量json_object恢复完整正文；最终所有带附件上下文请求使用json_object，无附件保持原配置。Prompt v8要求标题简短、正文独立段落，不向学习者展示内部参数。
