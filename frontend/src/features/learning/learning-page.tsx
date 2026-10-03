"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
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
  Copy,
  ArrowDown,
  RotateCcw,
  LoaderCircle,
  UserRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { AttachmentComposer } from "./attachment-composer";
import { useDraftAttachments } from "./use-draft-attachments";
import { HistoryAttachments } from "./history-attachments";
import { AnswerContent } from "./answer-content";
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
import { userProfileQueryOptions, userAvatarQueryOptions } from "@/features/user-profile/queries";
import {
  knowledgeBaseListQueryOptions,
  knowledgeFileListQueryOptions,
} from "@/features/file-management/queries";
import { ApiError } from "@/lib/api/errors";
import type { TurnView, ConversationCreate, ConversationDetail } from "./api";
import {
  conversationsQueryOptions,
  conversationQueryOptions,
  createConversationMutationOptions,
  streamQuestionMutationOptions,
  deleteConversationMutationOptions,
  renameConversationMutationOptions,
  feedbackMutationOptions,
  learningKeys,
  learningConsentQueryOptions,
  confirmLearningConsentMutationOptions,
} from "./queries";

export function answerError(code: string | null | undefined) {
  if (code === "ANSWER_SOURCE_CHANGED") return "资料发生变化，请重新提问。";
  if (code === "ANSWER_LEASE_EXPIRED" || code === "ANSWER_TIMEOUT") return "回答超时，请重试。";
  if (code === "ANSWER_LANGUAGE_INVALID") return "回答语言未通过校验，请重试。";
  if (code === "ANSWER_MARKDOWN_INVALID") return "回答格式未通过校验，请重试。";
  if (code === "ANSWER_CITATION_INVALID") return "回答未通过引用校验，请重试。";
  return "回答未完成，请重试。";
}

export function LearningPage() {
  const client = useQueryClient();
  const draft = useDraftAttachments();
  const profile = useQuery(userProfileQueryOptions());
  const avatar = useQuery(
    userAvatarQueryOptions(profile.data?.version ?? 0, Boolean(profile.data?.avatar_set)),
  );
  const [avatarPreview, setAvatarPreview] = useState<{ blob: Blob; url: string } | null>(null);
  const [failedAvatarUrl, setFailedAvatarUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!avatar.data || !profile.data?.avatar_set) {
      setAvatarPreview(null);
      return;
    }
    const url = URL.createObjectURL(avatar.data);
    setAvatarPreview({ blob: avatar.data, url });
    return () => URL.revokeObjectURL(url);
  }, [avatar.data, profile.data?.avatar_set]);
  const avatarUrl =
    profile.data?.avatar_set &&
    !avatar.isError &&
    avatarPreview?.blob === avatar.data &&
    avatarPreview?.url !== failedAvatarUrl
      ? avatarPreview?.url
      : null;
  const consent = useQuery(learningConsentQueryOptions());
  const confirmConsent = useMutation(confirmLearningConsentMutationOptions(client));
  const consentConfirmed =
    consent.data?.confirmed === true && consent.data.terms_version === "qwen-learning-v2";
  const [historyPage, setHistoryPage] = useState(1);
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState<"materials" | "general">("materials");
  const [kb, setKb] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [local, setLocal] = useState<{
    turn: TurnView;
    conversationId: string;
    scope: ConversationCreate;
  } | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [awayFromBottom, setAwayFromBottom] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const messageList = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => () => controller.current?.abort(), []);
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
  const create = useMutation(createConversationMutationOptions(client));
  const send = useMutation(streamQuestionMutationOptions(client));
  const rename = useMutation(renameConversationMutationOptions(client));
  const remove = useMutation(deleteConversationMutationOptions(client));
  const feedback = useMutation(feedbackMutationOptions(client));
  const active = detail.data?.conversation;
  const storedTurns = detail.data?.turns ?? [];
  const visibleLocal =
    local &&
    (!selected || local.conversationId === selected) &&
    !(
      local.turn.status === "succeeded" &&
      storedTurns.some(
        (turn) => turn.request_key === local.turn.request_key && turn.status === "succeeded",
      )
    )
      ? local
      : null;
  const turns = visibleLocal
    ? [
        ...storedTurns.filter((turn) => turn.request_key !== visibleLocal.turn.request_key),
        visibleLocal.turn,
      ]
    : storedTurns;
  const processing = turns.some((turn) => turn.status === "processing");
  const hasConversation = Boolean(selected || visibleLocal);

  useEffect(() => {
    if (follow.current && messageList.current) {
      messageList.current.scrollTop = messageList.current.scrollHeight;
    }
  }, [selected, local, detail.data]);

  function cancel() {
    controller.current?.abort();
    controller.current = null;
    setLocal(null);
    setStreamError(null);
    send.reset();
  }
  function reset() {
    cancel();
    draft.clear();
    setSelected("");
    setQuestion("");
    setFiles([]);
    follow.current = true;
    setAwayFromBottom(false);
  }
  function selectConversation(id: string) {
    cancel();
    draft.clear();
    setSelected(id);
    setQuestion("");
    follow.current = true;
    setAwayFromBottom(false);
  }
  async function ask(text: string, retry?: TurnView) {
    if (
      !consentConfirmed ||
      (!retry && draft.blocked) ||
      (!text.trim() && !(retry?.attachments?.length || draft.ready.length)) ||
      processing ||
      controller.current ||
      (!selected && mode === "materials" && !kb) ||
      (selected && !active)
    )
      return;
    const attachments = retry?.attachments ?? draft.ready;
    const abort = new AbortController();
    controller.current = abort;
    const key = retry?.request_key ?? crypto.randomUUID();
    const scope =
      visibleLocal?.turn.request_key === key
        ? visibleLocal.scope
        : ({
            mode,
            knowledge_base_id: mode === "materials" ? kb : null,
            file_ids: mode === "materials" ? files : [],
          } satisfies ConversationCreate);
    const snapshot: TurnView = {
      id: retry?.id ?? key,
      request_key: key,
      question: text.trim(),
      language: retry?.language ?? "zh",
      status: "processing",
      answer: null,
      refused: false,
      source_label: attachments.length
        ? active?.mode === "materials" || (!selected && mode === "materials")
          ? "用户资料与附件"
          : "用户附件"
        : active?.mode === "materials" || (!selected && mode === "materials")
          ? "用户资料"
          : "模型通用知识",
      citations: [],
      attachments,
      trace_id: null,
      trace_complete: false,
      error_code: null,
      feedback: null,
      created_at: retry?.created_at ?? new Date().toISOString(),
    };
    let id = selected;
    setLocal({ turn: snapshot, conversationId: id, scope });
    setStreamError(null);
    follow.current = true;
    setAwayFromBottom(false);
    try {
      if (!id) {
        const result = await create.mutateAsync(scope);
        if (controller.current !== abort || abort.signal.aborted) return;
        id = result.data.id;
        client.setQueryData(conversationQueryOptions(id).queryKey, {
          conversation: result.data,
          turns: [],
        });
        setSelected(id);
        setLocal((value) => (value ? { ...value, conversationId: id } : value));
      }
      await send.mutateAsync({
        id,
        body: {
          request_key: key,
          question: snapshot.question,
          attachment_ids: attachments.map((attachment) => attachment.id),
        },
        signal: abort.signal,
        receive: (event) => {
          if (controller.current !== abort || abort.signal.aborted) return;
          if (event.turn && event.turn.request_key !== key)
            throw new ApiError("回答与当前问题不一致");
          if (event.type === "started") {
            setQuestion("");
            draft.acknowledge(attachments.map((attachment) => attachment.id));
          }
          if (event.type === "completed" && event.turn) {
            const finalTurn = event.turn;
            client.setQueryData<ConversationDetail>(learningKeys.detail(id), (value) =>
              value
                ? {
                    ...value,
                    turns: [...value.turns.filter((turn) => turn.request_key !== key), finalTurn],
                  }
                : value,
            );
          }
          setLocal((value) => {
            if (!value || value.turn.request_key !== key) return value;
            if (event.type === "delta")
              return {
                ...value,
                turn: { ...value.turn, answer: (value.turn.answer ?? "") + (event.delta ?? "") },
              };
            if (event.turn) return { ...value, turn: event.turn };
            return value;
          });
          if (event.type === "completed") controller.current = null;
        },
      });
    } catch (error) {
      if (controller.current !== abort || abort.signal.aborted) return;
      setLocal((value) =>
        value
          ? {
              ...value,
              turn: {
                ...value.turn,
                status: "failed",
                answer: null,
                error_code: error instanceof ApiError ? (error.errorKey ?? null) : null,
              },
            }
          : value,
      );
      setStreamError(error instanceof ApiError ? error.message : "请求失败，请重试。");
    } finally {
      if (controller.current === abort) controller.current = null;
      abort.abort();
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }
  async function copyAnswer(turn: TurnView) {
    try {
      await navigator.clipboard.writeText(turn.answer ?? "");
      setCopied(turn.id);
    } catch {
      setStreamError("复制失败，请手动选择回答内容复制。");
    }
  }

  return (
    <ContentShell>
      <div className="flex min-h-[calc(100dvh-var(--app-header-height))] flex-col lg:h-[calc(100dvh-var(--app-header-height))] lg:min-h-0 lg:flex-row">
        <aside
          className="flex shrink-0 flex-col gap-5 border-b border-border bg-sidebar px-5 py-6 lg:w-[312px] lg:border-r lg:border-b-0"
          aria-label="问答历史"
        >
          <Button variant="brand" className="w-full justify-start" onClick={reset}>
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
            className={`shrink-0 ${hasConversation ? "border-b border-border bg-surface px-5 py-[18px] lg:h-[125px] lg:px-10 lg:py-3" : "px-5 pt-7 lg:px-11"}`}
          >
            {!hasConversation ? (
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
                  className={`m-1 flex min-h-16 items-start gap-2 rounded-md px-3 py-3 text-left ${hasConversation ? "lg:h-14 lg:min-h-14 lg:py-2" : ""} ${enabled ? "border border-border bg-surface" : "text-muted-foreground"}`}
                >
                  <Icon className="mt-0.5 size-4 shrink-0" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{label}</span>
                    <span className="mt-1 hidden truncate text-[11px] text-muted-foreground sm:block">
                      {description}
                      {enabled ? "" : " · 尚未开放"}
                    </span>
                  </span>
                </button>
              ))}
            </div>
            {hasConversation ? (
              <div className="mt-3 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="min-w-0 truncate">
                  {(active?.mode ?? mode) === "materials"
                    ? `资料模式 · ${bases.data?.data.find((base) => base.id === active?.knowledge_base_id)?.name ?? "当前知识库"} · ${active?.file_ids.length ? `${active.file_ids.length} 个文件` : "整个知识库"}`
                    : "通用模式 · 模型通用知识"}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="lg:h-6 lg:min-h-6 lg:px-2"
                  onClick={reset}
                >
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
                          setStreamError(null);
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
                          setStreamError(null);
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
                                      setStreamError(null);
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
                    {draft.items.length
                      ? "将结合上传附件与模型通用知识回答。"
                      : "回答来自模型通用知识，不使用您的资料。"}
                  </p>
                )}
              </div>
            )}
          </header>
          <div
            className="min-h-64 flex-1 space-y-[18px] overflow-y-auto px-4 py-[22px] lg:min-h-0 lg:px-6"
            ref={messageList}
            role="log"
            aria-label="消息列表"
            onScroll={() => {
              const element = messageList.current;
              if (!element) return;
              follow.current = element.scrollHeight - element.scrollTop - element.clientHeight < 96;
              setAwayFromBottom(!follow.current);
            }}
          >
            {selected && detail.isError ? (
              <p role="alert">
                会话读取失败
                <Button variant="ghost" onClick={() => void detail.refetch()}>
                  重试
                </Button>
              </p>
            ) : null}
            {selected && detail.isPending && !visibleLocal ? (
              <p role="status">正在读取会话…</p>
            ) : null}
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
              <article key={turn.id} className="w-full min-w-0 space-y-4">
                <div
                  data-message-role="user"
                  className="relative ml-auto w-fit max-w-[95%] pr-12 sm:max-w-[80%] xl:max-w-[min(80%,1200px)]"
                >
                  <span
                    className="absolute top-5 right-0 grid size-9 place-items-center rounded-full bg-sidebar"
                    aria-hidden="true"
                  >
                    {avatarUrl ? (
                      <img
                        src={avatarUrl}
                        alt=""
                        className="size-9 rounded-full object-cover"
                        onError={() => setFailedAvatarUrl(avatarUrl)}
                      />
                    ) : (
                      <UserRound className="size-4" />
                    )}
                  </span>
                  <span className="mb-1 block text-right text-[11px] text-muted-foreground">
                    你
                  </span>
                  <HistoryAttachments attachments={turn.attachments ?? []} />
                  <p className="rounded-md bg-[#F0F0EC] px-4 py-3 text-sm leading-7 whitespace-pre-wrap break-words">
                    {turn.question}
                  </p>
                </div>
                <div
                  data-message-role="assistant"
                  className="relative w-fit min-w-0 max-w-full pl-12 lg:max-w-[min(92%,1440px)]"
                >
                  <span
                    className="absolute top-5 left-0 grid size-9 place-items-center rounded-full bg-primary"
                    aria-hidden="true"
                  >
                    <Sparkles className="size-4" />
                  </span>
                  <span className="mb-1 block text-[11px] text-muted-foreground">
                    学面通AI · <span>{turn.source_label}</span>
                  </span>
                  <div className="rounded-md border border-[#F2C94C]/35 bg-[#FFF4D6] px-5 py-4 text-sm leading-7">
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
                      <div role="status" aria-label="正在回答">
                        {turn.answer ? <AnswerContent content={turn.answer} /> : null}
                        <span className="mt-1 inline-flex items-center gap-2 text-xs text-muted-foreground">
                          <LoaderCircle className="size-3.5 animate-spin" />
                          {turn.answer ? "正在生成…" : "正在思考…"}
                        </span>
                      </div>
                    ) : (
                      <div>
                        <p role="alert" className="text-sm text-destructive">
                          {visibleLocal?.turn.id === turn.id && streamError
                            ? streamError
                            : answerError(turn.error_code)}
                        </p>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          title="重试回答"
                          aria-label="重试回答"
                          disabled={processing}
                          onClick={() => void ask(turn.question, turn)}
                        >
                          <RotateCcw className="size-4" />
                        </Button>
                      </div>
                    )}
                  </div>
                  {turn.status === "succeeded" ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button
                        size="icon"
                        className="size-9 min-h-9"
                        variant="ghost"
                        title="继续追问"
                        aria-label="继续追问"
                        onClick={() => document.getElementById("learning-question")?.focus()}
                      >
                        <MessageCircle className="size-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        className="size-9 min-h-9"
                        variant={turn.feedback === "helpful" ? "brand" : "ghost"}
                        title="有帮助"
                        aria-label="有帮助"
                        aria-pressed={turn.feedback === "helpful"}
                        disabled={feedback.isPending}
                        onClick={() =>
                          feedback.mutate(
                            {
                              id: selected,
                              turnId: turn.id,
                              feedback: turn.feedback === "helpful" ? null : "helpful",
                            },
                            {
                              onSuccess: (result) =>
                                setLocal((value) =>
                                  value?.turn.id === turn.id
                                    ? { ...value, turn: result.data }
                                    : value,
                                ),
                            },
                          )
                        }
                      >
                        <ThumbsUp className="size-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        className="size-9 min-h-9"
                        variant={turn.feedback === "unhelpful" ? "brand" : "ghost"}
                        title="无帮助"
                        aria-label="无帮助"
                        aria-pressed={turn.feedback === "unhelpful"}
                        disabled={feedback.isPending}
                        onClick={() =>
                          feedback.mutate(
                            {
                              id: selected,
                              turnId: turn.id,
                              feedback: turn.feedback === "unhelpful" ? null : "unhelpful",
                            },
                            {
                              onSuccess: (result) =>
                                setLocal((value) =>
                                  value?.turn.id === turn.id
                                    ? { ...value, turn: result.data }
                                    : value,
                                ),
                            },
                          )
                        }
                      >
                        <ThumbsDown className="size-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        className="size-9 min-h-9"
                        variant="ghost"
                        title={copied === turn.id ? "已复制" : "复制回答"}
                        aria-label="复制回答"
                        onClick={() => void copyAnswer(turn)}
                      >
                        <Copy className="size-4" />
                      </Button>
                      {copied === turn.id ? (
                        <span role="status" className="self-center text-xs text-muted-foreground">
                          已复制
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
          {awayFromBottom ? (
            <Button
              type="button"
              className="mx-auto mb-2"
              size="sm"
              variant="outline"
              onClick={() => {
                follow.current = true;
                setAwayFromBottom(false);
                if (messageList.current)
                  messageList.current.scrollTop = messageList.current.scrollHeight;
              }}
            >
              <ArrowDown className="size-4" />
              回到底部
            </Button>
          ) : null}
          {streamError && visibleLocal?.turn.status !== "failed" ? (
            <p role="alert" className="px-5 py-2 text-sm text-destructive lg:px-10">
              {streamError}
            </p>
          ) : null}
          <div
            className={`shrink-0 px-5 pb-7 lg:px-11 ${hasConversation ? "border-t border-border bg-surface pt-3 lg:px-10 lg:pt-2.5 lg:pb-2.5" : ""}`}
          >
            {consent.isPending ? (
              <p role="status" className="mb-2 text-xs text-muted-foreground">
                正在读取 AI 处理说明…
              </p>
            ) : consent.isError ? (
              <p role="alert" className="mb-2 text-xs text-destructive">
                AI 处理说明读取失败，暂不能上传或发送。
                <Button variant="ghost" size="sm" onClick={() => void consent.refetch()}>
                  重试
                </Button>
              </p>
            ) : !consentConfirmed ? (
              <div className="mb-3 rounded-md border border-border bg-muted p-3">
                <p className="text-xs leading-6">{consent.data?.notice}</p>
                <Button
                  type="button"
                  variant="brand"
                  size="sm"
                  disabled={!consent.data || confirmConsent.isPending}
                  onClick={() => {
                    if (consent.data)
                      confirmConsent.mutate({
                        confirmed: true,
                        terms_version: consent.data.terms_version,
                      });
                  }}
                >
                  同意并继续
                </Button>
                {confirmConsent.isError ? (
                  <p role="alert" className="text-xs text-destructive">
                    确认失败，请重试。
                  </p>
                ) : null}
              </div>
            ) : null}
            <form onSubmit={submit}>
              <AttachmentComposer
                draft={draft}
                actions={
                  <Button
                    type="submit"
                    size="icon"
                    className="size-9 min-h-9 rounded-full"
                    title={processing ? "正在回答" : "发送问题"}
                    aria-label={processing ? "正在回答" : "发送问题"}
                    disabled={
                      processing ||
                      !consentConfirmed ||
                      draft.blocked ||
                      (!question.trim() && !draft.ready.length) ||
                      (!selected && mode === "materials" && !kb) ||
                      (Boolean(selected) && !active)
                    }
                  >
                    <Send className="size-3.5" />
                  </Button>
                }
                disabled={!consentConfirmed || processing || Boolean(selected && !active)}
              >
                <label htmlFor="learning-question" className="sr-only">
                  {hasConversation ? "继续提问" : "您的问题"}
                </label>
                <Textarea
                  id="learning-question"
                  value={question}
                  maxLength={2000}
                  rows={hasConversation ? 2 : 3}
                  className={`resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 ${hasConversation ? "min-h-12 lg:h-12 lg:min-h-12 lg:flex-1 lg:py-1" : "min-h-20"}`}
                  disabled={processing || (Boolean(selected) && !active)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      void ask(question);
                    }
                  }}
                  onChange={(event) => {
                    setQuestion(event.target.value);
                    setStreamError(null);
                    send.reset();
                  }}
                  placeholder={
                    selected
                      ? "继续追问，或补充新的场景…"
                      : "输入你的问题，支持粘贴代码、错误信息或具体场景…"
                  }
                />
              </AttachmentComposer>
            </form>
          </div>
        </section>
      </div>
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
