"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import {
  MessageCircle,
  Plus,
  Send,
  ThumbsDown,
  ThumbsUp,
  Sparkles,
  BookOpenText,
  ClipboardCheck,
  Pencil,
  Trash2,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { AnswerContent } from "./answer-content";
import { CheckboxField } from "@/components/ui/checkbox-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { ContentShell } from "@/features/file-management/content-shell";
import {
  knowledgeBaseListQueryOptions,
  knowledgeFileListQueryOptions,
} from "@/features/file-management/queries";
import { ApiError } from "@/lib/api/errors";
import type { TurnView } from "./api";
import {
  conversationsQueryOptions,
  conversationQueryOptions,
  learningConsentQueryOptions,
  createConversationMutationOptions,
  sendQuestionMutationOptions,
  deleteConversationMutationOptions,
  renameConversationMutationOptions,
  confirmLearningConsentMutationOptions,
  feedbackMutationOptions,
} from "./queries";

export function answerError(code: string | null | undefined) {
  if (code === "ANSWER_SOURCE_CHANGED") return "资料发生变化，请重新提问。";
  if (code === "ANSWER_LEASE_EXPIRED" || code === "ANSWER_TIMEOUT") return "回答超时，请重试。";
  if (code === "ANSWER_LANGUAGE_INVALID") return "回答语言未通过校验，请重试。";
  if (code === "ANSWER_CITATION_INVALID") return "回答未通过引用校验，请重试。";
  return "回答未完成，请重试。";
}

export function LearningPage() {
  const client = useQueryClient();
  const [historyPage, setHistoryPage] = useState(1);
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState<"materials" | "general">("materials");
  const [kb, setKb] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [question, setQuestion] = useState("");
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [source, setSource] = useState<TurnView["citations"][number] | null>(null);
  const history = useQuery(conversationsQueryOptions(historyPage));
  const detail = useQuery(conversationQueryOptions(selected));
  const bases = useQuery(knowledgeBaseListQueryOptions(1, 100));
  const documents = useQuery({
    ...knowledgeFileListQueryOptions(kb, 1, 100),
    enabled: Boolean(kb && !selected),
  });
  const consent = useQuery(learningConsentQueryOptions());
  const create = useMutation(createConversationMutationOptions(client));
  const send = useMutation(sendQuestionMutationOptions(client));
  const rename = useMutation(renameConversationMutationOptions(client));
  const remove = useMutation(deleteConversationMutationOptions(client));
  const confirm = useMutation(confirmLearningConsentMutationOptions(client));
  const feedback = useMutation(feedbackMutationOptions(client));
  const active = detail.data?.conversation;
  const turns = detail.data?.turns ?? [];
  const processing =
    send.isPending || create.isPending || turns.some((t) => t.status === "processing");
  const lastFailed = turns.findLast((t) => t.status === "failed");

  function reset() {
    setSelected("");
    setQuestion("");
    setPendingKey(null);
    setLanguage("zh");
    setFiles([]);
    send.reset();
  }
  function selectConversation(id: string) {
    setSelected(id);
    setQuestion("");
    setPendingKey(null);
    send.reset();
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || processing) return;
    if (!consent.data?.confirmed) {
      setConfirmed(false);
      setNoticeOpen(true);
      return;
    }
    let id = selected;
    const key = pendingKey ?? crypto.randomUUID();
    setPendingKey(key);
    try {
      if (!id) {
        const result = await create.mutateAsync({
          mode,
          knowledge_base_id: mode === "materials" ? kb : null,
          file_ids: mode === "materials" ? files : [],
        });
        id = result.data.id;
        setSelected(id);
      }
      await send.mutateAsync({
        id,
        body: { request_key: key, question: question.trim(), language },
      });
      setQuestion("");
      setPendingKey(null);
    } catch {
      /* Query 显示错误，保留问题与幂等 key。 */
    }
  }
  const error = create.error ?? send.error;

  return (
    <ContentShell>
      <div className="flex min-h-[calc(100dvh-76px)] flex-col lg:h-[calc(100dvh-76px)] lg:min-h-0 lg:flex-row">
        <aside
          className="flex shrink-0 flex-col gap-5 border-b border-border bg-sidebar px-5 py-6 lg:w-[312px] lg:border-r lg:border-b-0"
          aria-label="问答历史"
        >
          <Button
            variant="brand"
            className="w-full justify-start"
            onClick={reset}
            disabled={processing}
          >
            <Plus className="size-4" />
            新建会话
          </Button>
          <h2 className="text-[13px] text-muted-foreground">历史会话</h2>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {history.isPending ? (
              <p role="status" className="text-sm">
                正在读取历史…
              </p>
            ) : history.isError ? (
              <p role="alert">
                历史读取失败
                <Button variant="ghost" onClick={() => void history.refetch()}>
                  重试
                </Button>
              </p>
            ) : (
              <>
                <ul className="space-y-1.5">
                  {history.data.data.map((item) => (
                    <li key={item.id}>
                      <button
                        className={`flex w-full items-start gap-2 rounded-md px-3 py-3 text-left ${selected === item.id ? "bg-muted" : "hover:bg-surface"}`}
                        disabled={processing}
                        aria-label={item.title}
                        onClick={() => selectConversation(item.id)}
                      >
                        <MessageCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                        <span className="min-w-0">
                          <span className="block truncate text-sm">{item.title}</span>
                          <time
                            className="mt-1 block text-[11px] text-muted-foreground"
                            dateTime={item.updated_at}
                          >
                            {new Intl.DateTimeFormat("zh-CN", {
                              month: "numeric",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            }).format(new Date(item.updated_at))}
                          </time>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                {!history.data.data.length ? (
                  <p className="py-4 text-xs text-muted-foreground">第一段学习，从一个问题开始。</p>
                ) : null}
              </>
            )}
          </div>
          {selected ? (
            <div className="flex gap-2 border-t border-border pt-3">
              <Button
                variant="ghost"
                size="sm"
                disabled={!active || processing}
                onClick={() => {
                  setNewTitle(active?.title ?? "");
                  setRenameOpen(true);
                }}
              >
                <Pencil className="size-3.5" />
                重命名
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={!active || processing}
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 className="size-3.5" />
                删除会话
              </Button>
            </div>
          ) : null}
          {history.data && history.data.meta.total_pages > 1 ? (
            <div className="flex items-center justify-between">
              <Button
                size="sm"
                variant="ghost"
                disabled={historyPage <= 1 || processing}
                onClick={() => setHistoryPage((p) => p - 1)}
              >
                上一页
              </Button>
              <span className="text-xs">{historyPage}</span>
              <Button
                size="sm"
                variant="ghost"
                disabled={historyPage >= history.data.meta.total_pages || processing}
                onClick={() => setHistoryPage((p) => p + 1)}
              >
                下一页
              </Button>
            </div>
          ) : null}
        </aside>
        <section className="flex min-w-0 flex-1 flex-col" aria-label="快速回答">
          <header
            className={`shrink-0 ${selected ? "border-b border-border bg-surface px-5 py-[18px] lg:px-10" : "px-5 pt-7 lg:px-11"}`}
          >
            {!selected ? (
              <div className="mb-[22px]">
                <h1 className="text-[26px] font-semibold">学习室</h1>
                <p className="mt-2 text-[13px] text-muted-foreground">
                  选择合适的学习方式，再开始你的问题。
                </p>
              </div>
            ) : (
              <h1 className="sr-only">学习室 · 快速回答</h1>
            )}
            <div
              className="grid grid-cols-3 rounded-md bg-sidebar"
              role="group"
              aria-label="学习方式"
            >
              {[
                { label: "快速回答", detail: "即时解答与追问", Icon: Sparkles, active: true },
                {
                  label: "知识精讲",
                  detail: "结构化讲透知识点",
                  Icon: BookOpenText,
                  active: false,
                },
                {
                  label: "刷题评测",
                  detail: "创建题目并评估能力",
                  Icon: ClipboardCheck,
                  active: false,
                },
              ].map(({ label, detail: description, Icon, active: enabled }) => (
                <button
                  key={label}
                  type="button"
                  disabled={!enabled}
                  aria-pressed={enabled}
                  title={enabled ? undefined : `${label}尚未开放`}
                  className={`m-1 flex min-h-16 items-start gap-2 rounded-md px-3 py-3 text-left ${enabled ? "border border-border bg-surface" : "text-muted-foreground"}`}
                >
                  <Icon className="mt-0.5 size-4 shrink-0" />
                  <span>
                    <span className="block text-sm font-medium">{label}</span>
                    <span className="mt-1 hidden text-[11px] text-muted-foreground sm:block">
                      {description}
                      {enabled ? "" : " · 尚未开放"}
                    </span>
                  </span>
                </button>
              ))}
            </div>
            {selected ? (
              <div className="mt-3 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>
                  {active?.mode === "materials"
                    ? `资料模式 · ${bases.data?.data.find((base) => base.id === active?.knowledge_base_id)?.name ?? "当前知识库"} · ${active?.file_ids.length ? `${active.file_ids.length} 个文件` : "整个知识库"}`
                    : "通用模式 · 模型通用知识"}
                </span>
                <Button variant="ghost" size="sm" disabled={processing} onClick={reset}>
                  新建以修改来源
                </Button>
              </div>
            ) : (
              <div className="mt-[22px]">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium">知识来源</span>
                  <div
                    className="flex rounded-md border border-border bg-surface p-0.5"
                    role="group"
                    aria-label="知识使用模式"
                  >
                    {(["materials", "general"] as const).map((value) => (
                      <Button
                        key={value}
                        size="sm"
                        variant={mode === value ? "brand" : "ghost"}
                        aria-pressed={mode === value}
                        disabled={processing}
                        onClick={() => {
                          setMode(value);
                          setKb("");
                          setFiles([]);
                          setQuestion("");
                          setPendingKey(null);
                          send.reset();
                        }}
                      >
                        {value === "materials" ? "资料模式" : "通用模式"}
                      </Button>
                    ))}
                  </div>
                </div>
                {mode === "materials" ? (
                  <div className="grid items-start gap-3 sm:grid-cols-[minmax(180px,1fr)_minmax(0,1fr)]">
                    <div>
                      <span id="knowledge-base-label" className="sr-only">
                        知识库
                      </span>
                      <Select
                        value={kb}
                        onValueChange={(value) => {
                          setKb(value);
                          setFiles([]);
                          setQuestion("");
                          setPendingKey(null);
                        }}
                      >
                        <SelectTrigger aria-labelledby="knowledge-base-label">
                          <SelectValue placeholder="请选择知识库" />
                        </SelectTrigger>
                        <SelectContent>
                          {bases.data?.data.map((base) => (
                            <SelectItem key={base.id} value={base.id}>
                              {base.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {bases.isError ? (
                        <p role="alert">
                          知识库读取失败
                          <Button variant="ghost" onClick={() => void bases.refetch()}>
                            重试
                          </Button>
                        </p>
                      ) : null}
                    </div>
                    <div className="min-w-0">
                      {kb ? (
                        <>
                          {documents.isError ? (
                            <p role="alert">
                              资料列表读取失败
                              <Button variant="ghost" onClick={() => void documents.refetch()}>
                                重试
                              </Button>
                            </p>
                          ) : documents.isPending ? (
                            <p role="status">正在读取资料…</p>
                          ) : (
                            <div className="flex max-h-24 flex-wrap gap-1.5 overflow-auto">
                              {documents.data.data
                                .filter((file) => file.validation_status === "available")
                                .map((file) => (
                                  <button
                                    key={file.id}
                                    type="button"
                                    aria-pressed={files.includes(file.id)}
                                    onClick={() => {
                                      setFiles((current) =>
                                        current.includes(file.id)
                                          ? current.filter((id) => id !== file.id)
                                          : [...current, file.id],
                                      );
                                      setQuestion("");
                                      setPendingKey(null);
                                    }}
                                    className={`inline-flex max-w-full items-center gap-1 rounded border border-border px-2 py-1 text-[11px] ${files.includes(file.id) ? "bg-muted" : "bg-surface"}`}
                                  >
                                    <FileText className="size-3 shrink-0" />
                                    <span className="truncate">{file.display_name}</span>
                                  </button>
                                ))}
                            </div>
                          )}
                          <p className="mt-1 text-[11px] text-muted-foreground">
                            {documents.data && documents.data.meta.total > 100
                              ? "显示前 100 个文件；"
                              : ""}
                            不选文件时检索整个知识库。
                          </p>
                        </>
                      ) : (
                        <p className="pt-2 text-xs text-muted-foreground">
                          先选择知识库，再指定资料范围。
                        </p>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    回答来自模型通用知识，不使用您的资料。
                  </p>
                )}
              </div>
            )}
          </header>
          <div
            className="min-h-64 flex-1 space-y-[18px] overflow-y-auto px-5 py-[22px] lg:min-h-0 lg:px-10"
            aria-live="polite"
          >
            {selected && detail.isError ? (
              <p role="alert">
                会话读取失败
                <Button variant="ghost" onClick={() => void detail.refetch()}>
                  重试
                </Button>
              </p>
            ) : null}
            {selected && detail.isPending ? <p role="status">正在读取会话…</p> : null}
            {!turns.length && !selected ? (
              <div className="flex h-full min-h-48 flex-col items-center justify-center text-center">
                <span className="mb-4 grid size-12 place-items-center rounded-xl bg-muted">
                  <Sparkles className="size-5 text-accent-foreground" />
                </span>
                <h2 className="text-xl font-semibold">今天想弄懂什么？</h2>
                <p className="mt-2 text-xs text-muted-foreground">
                  {mode === "materials"
                    ? "基于已选资料回答，你可以持续追问。"
                    : "从通用知识开始，你可以持续追问。"}
                </p>
              </div>
            ) : null}
            {turns.map((turn) => (
              <article key={turn.id} className="space-y-[18px]">
                <div className="ml-auto max-w-[85%]">
                  <span className="mb-1 block text-right text-[11px] text-muted-foreground">
                    你
                  </span>
                  <p className="rounded-md bg-[#F0F0EC] px-4 py-3 text-[13px] whitespace-pre-wrap break-words">
                    {turn.question}
                  </p>
                </div>
                <div className="max-w-[90%]">
                  <span className="mb-1 block text-[11px] text-muted-foreground">
                    学面通AI · <span>{turn.source_label}</span>
                  </span>
                  <div className="rounded-md border border-[#F2C94C]/35 bg-[#FFF4D6] p-4">
                    {turn.status === "succeeded" ? (
                      <>
                        <AnswerContent content={turn.answer ?? ""} />
                        {turn.citations.length ? (
                          <div className="mt-4 rounded-md border border-border bg-surface p-3">
                            <p className="mb-2 text-[11px] text-muted-foreground">引用资料</p>
                            <div className="grid gap-1">
                              {turn.citations.map((citation) => (
                                <button
                                  key={citation.number}
                                  aria-label={`[${citation.number}] ${citation.available ? citation.evidence?.file_name : "来源已失效"}`}
                                  type="button"
                                  disabled={!citation.available}
                                  onClick={() => setSource(citation)}
                                  className="text-left text-xs text-[#496B86] hover:underline disabled:text-muted-foreground"
                                >
                                  <span className="mr-2 text-accent-foreground">
                                    [{citation.number}]
                                  </span>
                                  {citation.available ? citation.evidence?.file_name : "来源已失效"}
                                  {citation.evidence?.page_start
                                    ? ` · 第 ${citation.evidence.page_start} 页`
                                    : citation.evidence?.paragraph_start
                                      ? ` · 第 ${citation.evidence.paragraph_start} 段`
                                      : ""}
                                </button>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </>
                    ) : turn.status === "processing" ? (
                      <p role="status" className="text-sm text-muted-foreground">
                        正在检索与生成回答，请稍候…
                      </p>
                    ) : (
                      <p className="text-sm text-destructive">{answerError(turn.error_code)}</p>
                    )}
                  </div>
                  {turn.status === "succeeded" ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="brand"
                        onClick={() => document.getElementById("learning-question")?.focus()}
                      >
                        <MessageCircle className="size-3.5" />
                        继续追问
                      </Button>
                      <Button
                        size="sm"
                        variant={turn.feedback === "helpful" ? "brand" : "outline"}
                        aria-pressed={turn.feedback === "helpful"}
                        disabled={feedback.isPending}
                        onClick={() =>
                          feedback.mutate({
                            id: selected,
                            turnId: turn.id,
                            feedback: turn.feedback === "helpful" ? null : "helpful",
                          })
                        }
                      >
                        <ThumbsUp className="size-3.5" />
                        有帮助
                      </Button>
                      <Button
                        size="sm"
                        variant={turn.feedback === "unhelpful" ? "brand" : "outline"}
                        aria-pressed={turn.feedback === "unhelpful"}
                        disabled={feedback.isPending}
                        onClick={() =>
                          feedback.mutate({
                            id: selected,
                            turnId: turn.id,
                            feedback: turn.feedback === "unhelpful" ? null : "unhelpful",
                          })
                        }
                      >
                        <ThumbsDown className="size-3.5" />
                        无帮助
                      </Button>
                      <Button size="sm" variant="outline" disabled title="生成笔记尚未开放">
                        生成笔记
                      </Button>
                    </div>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
          <div
            className={`shrink-0 px-5 pb-7 lg:px-11 ${selected ? "border-t border-border bg-surface pt-3" : ""}`}
          >
            <form onSubmit={submit} className="rounded-md border border-border bg-surface p-3">
              <label htmlFor="learning-question" className="sr-only">
                {selected ? "继续提问" : "您的问题"}
              </label>
              <Textarea
                id="learning-question"
                value={question}
                maxLength={2000}
                rows={selected ? 2 : 3}
                className={`resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 ${selected ? "min-h-12" : "min-h-20"}`}
                disabled={processing || (Boolean(selected) && !active)}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  setPendingKey(null);
                  send.reset();
                }}
                placeholder={
                  selected
                    ? "继续追问，或补充新的场景…"
                    : "输入你的问题，支持粘贴代码、错误信息或具体场景…"
                }
              />
              {error ? (
                <p role="alert" className="my-2 text-sm text-destructive">
                  {error instanceof ApiError ? error.message : "请求失败，请重试。"}
                </p>
              ) : null}
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span id="answer-language-label" className="sr-only">
                    回答语言
                  </span>
                  <Select
                    value={language}
                    onValueChange={(value) => {
                      setLanguage(value as "zh" | "en");
                      setPendingKey(null);
                    }}
                    disabled={processing}
                  >
                    <SelectTrigger
                      className="h-8 w-28 text-xs"
                      aria-labelledby="answer-language-label"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="zh">中文</SelectItem>
                      <SelectItem value="en">English</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="hidden text-[11px] text-muted-foreground xl:block">
                    AI 回答可能有误，请结合来源核对。
                  </p>
                </div>
                <div className="flex gap-2">
                  {lastFailed && !processing ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setQuestion(lastFailed.question);
                        setLanguage(lastFailed.language);
                        setPendingKey(lastFailed.request_key);
                        send.reset();
                      }}
                    >
                      重试上次问题
                    </Button>
                  ) : null}
                  <Button
                    type="submit"
                    size="sm"
                    disabled={
                      processing ||
                      !question.trim() ||
                      consent.isPending ||
                      consent.isError ||
                      (!selected && mode === "materials" && !kb) ||
                      (Boolean(selected) && !active)
                    }
                  >
                    <Send className="size-3.5" />
                    {processing ? "正在回答…" : "发送问题"}
                  </Button>
                </div>
              </div>
              {consent.isError ? (
                <p role="alert">
                  AI 说明读取失败
                  <Button variant="ghost" type="button" onClick={() => void consent.refetch()}>
                    重试
                  </Button>
                </p>
              ) : null}
            </form>
          </div>
        </section>
      </div>
      <Dialog open={noticeOpen} onOpenChange={setNoticeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认 AI 问答处理说明</DialogTitle>
            <DialogDescription>{consent.data?.notice}</DialogDescription>
          </DialogHeader>
          <CheckboxField
            checked={confirmed}
            onCheckedChange={(value) => setConfirmed(value === true)}
            label="我已阅读并确认有权处理这些内容"
          />
          <DialogFooter>
            <Button
              disabled={!confirmed || confirm.isPending || !consent.data}
              onClick={() => {
                if (consent.data)
                  confirm.mutate(
                    { confirmed: true, terms_version: consent.data.terms_version },
                    { onSuccess: () => setNoticeOpen(false) },
                  );
              }}
            >
              确认
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名会话</DialogTitle>
            <DialogDescription>方便之后找到这次学习记录。</DialogDescription>
          </DialogHeader>
          <Input
            aria-label="会话标题"
            value={newTitle}
            maxLength={80}
            onChange={(event) => setNewTitle(event.target.value)}
          />
          <DialogFooter>
            <Button
              disabled={!newTitle.trim() || rename.isPending}
              onClick={() =>
                rename.mutate(
                  { id: selected, title: newTitle.trim() },
                  { onSuccess: () => setRenameOpen(false) },
                )
              }
            >
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除这段会话？</DialogTitle>
            <DialogDescription>删除后不会出现在历史列表中，首期不提供恢复入口。</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              取消
            </Button>
            <Button
              variant="brand"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(selected, {
                  onSuccess: () => {
                    setDeleteOpen(false);
                    reset();
                  },
                })
              }
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={Boolean(source)}
        onOpenChange={(open) => {
          if (!open) setSource(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              来源 [{source?.number}] · {source?.evidence?.file_name}
            </DialogTitle>
            <DialogDescription>
              {source?.evidence?.heading_path.join(" / ") || "资料片段"}
            </DialogDescription>
          </DialogHeader>
          <p className="max-h-[60dvh] overflow-auto whitespace-pre-wrap text-sm leading-7">
            {source?.evidence?.content}
          </p>
        </DialogContent>
      </Dialog>
    </ContentShell>
  );
}
