"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type {
  DefinitionView,
  DraftPatch,
  PreviewRequest,
  VersionSummary,
  VersionView,
} from "./api";
import { registeredContractRecord } from "./contract-metadata";
import { usePromptDraftMemory, type EditorForm } from "./draft-memory";
import { dateText, JsonView, PromptError, VersionBadge } from "./display";
import {
  evaluatePromptOptions,
  patchPromptDraftOptions,
  previewPromptOptions,
  promptDiffOptions,
  promptStatusOptions,
  publishPromptOptions,
  rollbackPromptOptions,
} from "./queries";

function formFor(version: VersionView): EditorForm {
  return {
    content: version.content,
    variables: JSON.stringify(version.variables, null, 2),
    dependencies: JSON.stringify(
      version.dependencies.map(({ version_id, slot, position }) => ({
        version_id,
        slot,
        position,
      })),
      null,
      2,
    ),
    change: version.change_description,
  };
}
function jsonArray(value: string, label: string): unknown[] {
  const parsed: unknown = JSON.parse(value);
  if (!Array.isArray(parsed)) throw new Error(`${label}必须是 JSON 数组`);
  return parsed;
}
function previewVariables(value: string): NonNullable<PreviewRequest["variables"]> {
  const parsed: unknown = JSON.parse(value);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed))
    throw new Error("合成变量必须是 JSON 对象");
  return parsed as NonNullable<PreviewRequest["variables"]>;
}
const SYNTHETIC_PREVIEW = JSON.stringify(
  {
    config: {
      mode: "practice",
      source_mode: "general",
      topic: "合成事务原子性",
      question_count: 1,
      question_types: { single_choice: 1 },
      difficulty: "medium",
      knowledge_base_id: null,
      file_ids: [],
    },
    request: {},
    selected_asset: {},
    weakness: {},
    profile: {},
    defaults: {},
  },
  null,
  2,
);

type Confirmation = {
  type: "publish" | "rollback" | "status";
  active: string | null;
  revision: number;
  target?: string;
  runtime?: DefinitionView["runtime_status"];
};

/** 编辑内容只保存在本组件内存。服务端冲突不会重置草稿或重新选择发布基准。 */
export function VersionEditor({
  definition,
  version,
  timeline,
  onDirty,
  onReload,
  onVersion,
  reloading = false,
}: {
  definition: DefinitionView;
  version: VersionView;
  timeline: VersionSummary[];
  onDirty: (dirty: boolean) => void;
  onReload: () => void;
  onVersion: (id: string) => void;
  reloading?: boolean;
}) {
  const client = useQueryClient();
  const memory = usePromptDraftMemory();
  const [restored] = useState(() => memory.read(version.id));
  const [form, setForm] = useState(() => restored?.form ?? formFor(version));
  const [saved, setSaved] = useState(() => restored?.saved ?? formFor(version));
  const [revision, setRevision] = useState(restored?.revision ?? version.revision);
  const [savedHash, setSavedHash] = useState(restored?.savedHash ?? version.content_sha256);
  const [localError, setLocalError] = useState("");
  const [previewInput, setPreviewInput] = useState(SYNTHETIC_PREVIEW);
  const [showDiff, setShowDiff] = useState(false);
  const [base, setBase] = useState(version.base_active_version_id ?? "none");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState(
    version.status === "draft"
      ? (timeline.find((item) => item.status !== "draft")?.id ?? "")
      : version.id,
  );
  const [reason, setReason] = useState("");
  const patch = useMutation(patchPromptDraftOptions(client, version.id));
  const preview = useMutation(previewPromptOptions(client, version.id));
  const evaluate = useMutation(evaluatePromptOptions(client, version.id));
  const publish = useMutation(publishPromptOptions(client, version.id));
  const rollback = useMutation(rollbackPromptOptions(client, definition.id));
  const status = useMutation(promptStatusOptions(client, definition.id));
  const diff = useQuery(
    promptDiffOptions(version.id, base === "none" ? undefined : base, showDiff),
  );
  const dirty = JSON.stringify(form) !== JSON.stringify(saved);
  const contract = registeredContractRecord(definition);
  const canManage = contract !== null;
  const isDraft = version.status === "draft" && canManage;
  const busy =
    reloading ||
    patch.isPending ||
    evaluate.isPending ||
    publish.isPending ||
    rollback.isPending ||
    status.isPending;
  const tools = Array.isArray(contract?.tools)
    ? contract.tools.filter((item): item is string => typeof item === "string")
    : [];
  const evaluation = evaluate.data?.data ?? version.latest_evaluation;

  useEffect(() => {
    if (dirty)
      memory.write(version.id, {
        definitionId: version.definition_id,
        form,
        saved,
        revision,
        savedHash,
      });
    else memory.remove(version.id);
  }, [dirty, form, saved, revision, savedHash, memory, version.id, version.definition_id]);

  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);
  useEffect(() => {
    if (!dirty) return;
    const leave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, [dirty]);

  function edit(field: keyof EditorForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setLocalError("");
  }
  async function save() {
    setLocalError("");
    try {
      // 此处只校验JSON结构；变量白名单、依赖与业务规则由真实后端唯一校验。
      const body: DraftPatch = {
        expected_revision: revision,
        content: form.content,
        variables: jsonArray(form.variables, "变量契约") as DraftPatch["variables"],
        dependencies: jsonArray(form.dependencies, "依赖版本") as DraftPatch["dependencies"],
        change_description: form.change,
      };
      const result = await patch.mutateAsync(body);
      const next = formFor(result.data);
      setForm(next);
      setSaved(next);
      setRevision(result.data.revision);
      setSavedHash(result.data.content_sha256);
      preview.reset();
      evaluate.reset();
    } catch (error) {
      if (!(error instanceof Error) || error.name !== "ApiError")
        setLocalError("JSON 格式无效，请检查变量和依赖数组。");
    }
  }
  async function runPreview() {
    setLocalError("");
    try {
      await preview.mutateAsync({ variables: previewVariables(previewInput) });
    } catch (error) {
      if (!(error instanceof Error) || error.name !== "ApiError")
        setLocalError("合成变量必须是合法 JSON 对象。");
    }
  }
  async function confirm() {
    if (!confirmation) return;
    try {
      if (confirmation.type === "publish")
        await publish.mutateAsync({
          expected_active_version_id: confirmation.active,
          expected_revision: confirmation.revision,
        });
      if (confirmation.type === "rollback" && confirmation.target) {
        const result = await rollback.mutateAsync({
          expected_active_version_id: confirmation.active,
          target_version_id: confirmation.target,
          reason: reason.trim(),
        });
        onVersion(result.data.id);
      }
      if (confirmation.type === "status")
        await status.mutateAsync({
          expected_active_version_id: confirmation.active,
          runtime_status: confirmation.runtime!,
        });
      setConfirmation(null);
    } catch {
      /* 真实错误由下面的共享ApiError展示，不自动改变版本基准。 */
    }
  }
  const errors = [
    patch.error,
    preview.error,
    evaluate.error,
    publish.error,
    rollback.error,
    status.error,
  ].filter(Boolean);
  return (
    <div className="min-w-0 space-y-7">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-5">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">版本 v{version.version}</h2>
          <VersionBadge status={version.status} />
          <Badge variant="outline">修订 {revision}</Badge>
          {dirty && <Badge variant="warm">未保存</Badge>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={busy} onClick={onReload}>
            重新加载版本
          </Button>
          <Button
            variant="outline"
            disabled={busy || dirty || !canManage}
            onClick={() =>
              setConfirmation({
                type: "status",
                active: definition.active_version_id,
                revision,
                runtime: definition.runtime_status === "enabled" ? "disabled" : "enabled",
              })
            }
          >
            {definition.runtime_status === "enabled" ? "停用新任务" : "启用新任务"}
          </Button>
          {isDraft && (
            <Button disabled={busy || !dirty || !form.change.trim()} onClick={() => void save()}>
              {patch.isPending ? "保存中…" : "保存草稿"}
            </Button>
          )}
        </div>
      </div>
      {restored && dirty && (
        <p role="status" className="text-sm text-muted-foreground">
          已恢复此后台会话的未保存草稿，原编辑基准保持不变。
        </p>
      )}
      {localError && (
        <p role="alert" className="text-sm text-danger">
          {localError}
        </p>
      )}
      {errors.map((error, index) => (
        <PromptError key={index} error={error} />
      ))}
      {patch.isSuccess && !dirty && (
        <p role="status" className="text-sm text-success">
          草稿已保存；修改后需重新执行固定评测。
        </p>
      )}
      {publish.isSuccess && (
        <p role="status" className="text-sm text-success">
          版本已发布，后续新任务使用该版本。
        </p>
      )}
      {status.isSuccess && (
        <p role="status" className="text-sm text-success">
          运行状态已更新，已有任务仍使用入队快照。
        </p>
      )}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(240px,1fr)]">
        <div className="space-y-5">
          <div className="grid gap-2">
            <Label htmlFor="prompt-content">Prompt 正文</Label>
            <Textarea
              id="prompt-content"
              className="min-h-80 max-h-[560px] overflow-y-auto font-mono text-sm [field-sizing:fixed]"
              value={form.content}
              readOnly={!isDraft}
              disabled={busy}
              onChange={(event) => edit("content", event.target.value)}
              maxLength={20000}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="prompt-change">变更说明</Label>
            <Textarea
              id="prompt-change"
              value={form.change}
              readOnly={!isDraft}
              disabled={busy}
              onChange={(event) => edit("change", event.target.value)}
              maxLength={1000}
            />
          </div>
        </div>
        <aside className="min-w-0 space-y-4 border-l border-border pl-5 text-sm">
          <h3 className="font-semibold">代码能力边界</h3>
          <p className="text-muted-foreground">{definition.description}</p>
          <div>
            <p className="text-xs text-muted-foreground">场景</p>
            <p className="mt-1 break-all font-mono text-xs">{definition.definition_key}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">允许工具</p>
            <p className="mt-1">
              {!contract ? "历史注册契约不可用" : tools.length ? tools.join("、") : "无工具权限"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">场景契约 SHA-256</p>
            <p className="mt-1 break-all font-mono text-xs">
              {definition.contract_sha256 ?? "历史契约不可用"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">已保存正文 SHA-256</p>
            <p className="mt-1 break-all font-mono text-xs">{savedHash}</p>
          </div>
          <p className="text-xs text-muted-foreground">
            创建：{dateText(version.created_at)}
            <br />
            发布：{dateText(version.published_at)}
          </p>
        </aside>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="prompt-variables">变量契约 · JSON</Label>
          <Textarea
            id="prompt-variables"
            className="min-h-48 max-h-80 overflow-y-auto font-mono text-xs [field-sizing:fixed]"
            value={form.variables}
            readOnly={!isDraft}
            disabled={busy}
            onChange={(event) => edit("variables", event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            只允许代码注册的变量和简单占位符，不能新增表达式或工具。
          </p>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="prompt-dependencies">固定依赖版本 · JSON</Label>
          <Textarea
            id="prompt-dependencies"
            className="min-h-48 max-h-80 overflow-y-auto font-mono text-xs [field-sizing:fixed]"
            value={form.dependencies}
            readOnly={!isDraft}
            disabled={busy}
            onChange={(event) => edit("dependencies", event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            version_id、slot、position 固定到已发布版本，不解析“最新版本”。
          </p>
        </div>
      </div>
      <section className="space-y-4 border-t border-border pt-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="font-semibold">版本 Diff</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              比较已保存的版本；未保存修改不包含在 Diff 中。
            </p>
          </div>
          <Button variant="outline" onClick={() => setShowDiff(!showDiff)}>
            {showDiff ? "收起 Diff" : "查看 Diff"}
          </Button>
        </div>
        {showDiff && (
          <>
            <div className="max-w-sm">
              <Label htmlFor="diff-base">对比基准版本</Label>
              <Select value={base} onValueChange={setBase}>
                <SelectTrigger id="diff-base" className="mt-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">后端默认基准</SelectItem>
                  {timeline
                    .filter((item) => item.id !== version.id)
                    .map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        v{item.version} · {item.status}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            {diff.isPending ? (
              <p className="text-sm text-muted-foreground">正在读取 Diff…</p>
            ) : diff.isError ? (
              <PromptError error={diff.error} />
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  变量{diff.data.variables_changed ? "已变化" : "未变化"} · 依赖
                  {diff.data.dependencies_changed ? "已变化" : "未变化"}
                </p>
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-sidebar/40 p-4 text-xs leading-6">
                  {diff.data.content_diff || "正文无差异"}
                </pre>
              </>
            )}
          </>
        )}
      </section>
      <section className="space-y-4 border-t border-border pt-6">
        <h3 className="font-semibold">合成预览</h3>
        <p className="text-sm text-muted-foreground">
          使用合成变量检查消息角色、依赖与 Schema，不调用模型。请勿输入真实用户资料。
        </p>
        <Label htmlFor="synthetic-variables">合成变量 · JSON</Label>
        <Textarea
          id="synthetic-variables"
          className="min-h-48 max-h-80 overflow-y-auto font-mono text-xs [field-sizing:fixed]"
          value={previewInput}
          onChange={(event) => {
            setPreviewInput(event.target.value);
            preview.reset();
          }}
        />
        <Button
          variant="outline"
          disabled={dirty || busy || preview.isPending || !canManage}
          onClick={() => void runPreview()}
        >
          {preview.isPending ? "预览中…" : "生成无模型预览"}
        </Button>
        {dirty && (
          <p className="text-xs text-muted-foreground">请先保存草稿，再预览、评测或发布。</p>
        )}
        {preview.data && (
          <div className="space-y-4">
            <p className="text-xs text-muted-foreground">
              动态输出 Schema SHA-256：
              <span className="break-all font-mono">{preview.data.data.output_schema_sha256}</span>
            </p>
            <JsonView value={preview.data.data.composition} />
            {preview.data.data.system_messages.map((message, index) => (
              <div key={index}>
                <p className="mb-2 text-xs font-semibold">
                  system {index + 1} · {preview.data!.data.message_lengths[index]} 字符
                </p>
                <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-surface p-3 text-xs leading-6">
                  {message}
                </pre>
              </div>
            ))}
            <p className="text-xs font-semibold">合成 data message</p>
            <JsonView value={preview.data.data.data_message} />
          </div>
        )}
      </section>
      <section className="space-y-4 border-t border-border pt-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">固定模型评测</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              显式调用实际配置模型及固定合成样例，会产生模型用量；保存草稿不会触发评测。
            </p>
          </div>
          <Button
            variant="outline"
            disabled={dirty || busy || !canManage}
            onClick={() => void evaluate.mutateAsync().catch(() => undefined)}
          >
            {evaluate.isPending ? "评测中…" : "执行固定评测"}
          </Button>
        </div>
        {evaluation ? (
          <>
            <div className="flex flex-wrap gap-2">
              <Badge variant={evaluation.passed ? "success" : "danger"}>
                {evaluation.passed ? "已通过" : "未通过"}
              </Badge>
              <Badge variant="outline">{evaluation.status}</Badge>
            </div>
            <p className="text-xs text-muted-foreground">完整评测指纹</p>
            <p className="break-all font-mono text-xs">{evaluation.evaluation_fingerprint}</p>
            <p className="text-xs text-muted-foreground">模型配置与用量指标</p>
            <JsonView
              value={{ model: evaluation.model_configuration, metrics: evaluation.metrics }}
            />
            <p className="text-xs text-muted-foreground">逐样例结果</p>
            <JsonView value={evaluation.case_results} />
            {evaluation.error_key && (
              <p className="text-sm text-danger">失败原因：{evaluation.error_key}</p>
            )}
            <p className="text-xs text-muted-foreground">
              发布时服务器再次核验完整指纹；历史通过结果不等于当前版本可发布。
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">尚无固定评测结果。</p>
        )}
      </section>
      <section className="flex flex-wrap items-end justify-between gap-4 border-t border-border pt-6">
        <div>
          <h3 className="font-semibold">发布与审计式回滚</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            回滚复制历史内容并产生新递增版本；证据失效时新版本保持草稿。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {isDraft && (
            <Button
              disabled={dirty || busy || !evaluation?.passed}
              onClick={() =>
                setConfirmation({
                  type: "publish",
                  active: version.base_active_version_id,
                  revision,
                })
              }
            >
              发布此版本
            </Button>
          )}
          <Select value={rollbackTarget} onValueChange={setRollbackTarget}>
            <SelectTrigger aria-label="回滚历史目标" className="w-44">
              <SelectValue placeholder="选择历史版本" />
            </SelectTrigger>
            <SelectContent>
              {timeline
                .filter((item) => item.status !== "draft")
                .map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    回滚目标 v{item.version}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            disabled={!rollbackTarget || dirty || busy || !canManage}
            onClick={() => {
              setReason("");
              setConfirmation({
                type: "rollback",
                active: definition.active_version_id,
                revision,
                target: rollbackTarget,
              });
            }}
          >
            回滚为新版本
          </Button>
        </div>
      </section>
      <Dialog
        open={confirmation !== null}
        onOpenChange={(open) => {
          if (!open && !busy) setConfirmation(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirmation?.type === "publish"
                ? `发布 v${version.version}`
                : confirmation?.type === "rollback"
                  ? "回滚并创建新版本"
                  : definition.runtime_status === "enabled"
                    ? "停用新任务入口"
                    : "启用新任务入口"}
            </DialogTitle>
            <DialogDescription>
              {confirmation?.type === "publish"
                ? "将替换活动发布版本；已入队任务继续使用原快照。服务器会核验基准、修订和评测指纹。"
                : confirmation?.type === "rollback"
                  ? `将从历史目标复制内容，创建下一整数版本；当前已读取最大版本为 v${Math.max(version.version, ...timeline.map((item) => item.version))}，最终新版本号由服务器分配。`
                  : "只影响新的运行；已有任务和历史结果保持原快照。"}
            </DialogDescription>
          </DialogHeader>
          {confirmation?.type === "rollback" && (
            <div className="grid gap-2">
              <Label htmlFor="rollback-reason">回滚原因（必填）</Label>
              <Textarea
                id="rollback-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                maxLength={1000}
              />
            </div>
          )}
          {confirmation && (
            <p className="break-all text-xs text-muted-foreground">
              提交基准：{confirmation.active ?? "尚无活动版本"}
            </p>
          )}
          {(publish.error || rollback.error || status.error) && (
            <PromptError error={publish.error || rollback.error || status.error} />
          )}
          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setConfirmation(null)}>
              取消
            </Button>
            <Button
              disabled={busy || (confirmation?.type === "rollback" && !reason.trim())}
              onClick={() => void confirm()}
            >
              {busy ? "提交中…" : "确认操作"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
