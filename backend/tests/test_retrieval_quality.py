import asyncio
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from test_document_integration import seed

from xuemian_ai.document_processing.evaluation import percentile95, ranking_metrics
from xuemian_ai.document_processing.models import BackgroundTask, DocumentChunk, RetrievalTrace
from xuemian_ai.document_processing.retrieval import RetrievalService
from xuemian_ai.document_processing.schemas import RetrievalRequest
from xuemian_ai.file_management.models import FileAsset, KnowledgeBaseFile
from xuemian_ai.learning.generation import InputContext, QwenAnswerProvider

REPO_ROOT = Path(__file__).resolve().parents[2]

pytest_plugins = ["test_document_integration"]

# 完全合成，不取用用户原件。每个 topic 是独立 TXT 文档。
CORPUS = [
    (
        "事务隔离防止并发事务读取未提交数据，即脏读。PostgreSQL 的 Read "
        "Committed 隔离级别不允许脏读，但允许不可重复读。",
        "Read Committed 是否允许脏读？",
        "未提交的修改会被另一个事务看到吗？",
    ),
    (
        "Redis 的 TTL 是键的剩余生存时间。EXPIRE 命令设置键的过期秒数，时间到达后该键会被删除。",
        "Redis TTL 是什么？",
        "缓存键怎样在指定秒数后自动失效？",
    ),
    (
        "Python asyncio 采用事件循环调度协程。await 会在等待 I/O"
        " 时让出执行权，使其他协程继续运行；不能自动把 CPU 密集计算变成并行执行。",
        "Python asyncio 如何调度协程？",
        "异步程序等待网络时怎么让别的任务继续执行？",
    ),
    (
        "HTTP 404 表示请求的资源不存在，401 表示缺少有效身份认证，403 表"
        "示没有访问权限。404 不代表服务器内部异常。",
        "HTTP 404 是什么意思？",
        "访问一个不存在的网址会返回哪个状态码？",
    ),
    (
        "二分查找要求数据有序，每次将查找范围缩小一半，时间复杂度为 O(log n)。"
        "未排序数组不能直接使用二分查找。",
        "二分查找要求什么条件？",
        "为什么折半查找不能直接用于乱序数组？",
    ),
    (
        "JWT access token 是短期访问凭证；refresh token 用"
        "于换取新访问凭证。刷新令牌泄露需要撤销会话，不应把它保存在公开日志中。",
        "refresh token 有什么作用？",
        "短期访问凭证到期后用什么换取新的凭证？",
    ),
    (
        "数据库索引可以减少检索扫描，但写入时也需要维护索引，会增加存储和写入成本。不是索引越多查询就一定越快。",
        "数据库索引有哪些成本？",
        "为什么不能给数据库所有列都随意增加索引？",
    ),
    (
        "RAG 资料问答先检索证据，再基于证据生成回答。引用必须能定位到真实文件和页码或"
        "段落；证据不足时应明确拒答，不能虚构来源。",
        "RAG 的引用有什么要求？",
        "资料找不到依据时问答系统应该怎么办？",
    ),
]
NEGATIVES = [
    "太阳到海王星的距离是多少？",
    "请给出法国红酒的酿造工艺参数。",
    "这份资料中公司 2030 年利润具体是多少？",
]


def test_ranking_metrics_count_unique_hits_and_real_rank() -> None:
    assert ranking_metrics(["wrong", "right", "right"], {"right"}) == {
        "recall": 1.0,
        "mrr": 0.5,
        "ndcg": 1 / math.log2(3),
    }
    assert percentile95([1, 2, 3, 4]) == 4


@pytest.mark.skipif(
    not os.getenv("RETRIEVAL_REAL_QUALITY"),
    reason="explicit real-model synthetic retrieval evaluation required",
)
async def test_real_chinese_fixed_golden_set_and_stage_ablation(context) -> None:
    settings, sessions, store = context
    settings = settings.model_copy(update={"document_provider": "qwen"})
    evaluation_context = settings, sessions, store
    owner = None
    kb = None
    file_ids = []
    for text, _, _ in CORPUS:
        (user, base, binding, asset, task), worker = await seed(evaluation_context, text.encode())
        if owner is None:
            owner, kb = user.id, base
        else:
            async with sessions() as session, session.begin():
                source = await session.get(FileAsset, asset)
                source.owner_user_id = owner
                association = await session.get(KnowledgeBaseFile, binding)
                association.knowledge_base_id = kb
                job = await session.get(BackgroundTask, task)
                job.user_id = owner
        assert await worker.run_once()
        async with sessions() as session:
            job = await session.get(BackgroundTask, task)
            assert job.status == "succeeded", job.last_error_code
        file_ids.append(binding)
    async with sessions() as session:
        rows = (
            await session.execute(
                select(DocumentChunk.id, KnowledgeBaseFile.id)
                .join(
                    KnowledgeBaseFile,
                    KnowledgeBaseFile.file_asset_id == DocumentChunk.file_asset_id,
                )
                .where(KnowledgeBaseFile.id.in_(file_ids))
            )
        ).all()
        relevant = {
            file: {str(chunk) for chunk, matched in rows if matched == file} for file in file_ids
        }
    metrics = {mode: [] for mode in ("FTS-only", "Vector-only", "Hybrid-only", "No-Rerank", "Full")}
    latencies = {mode: [] for mode in metrics}
    no_answer = {mode: [] for mode in metrics}
    locations = []
    errors = []
    generated_refusals = []
    for index, question in enumerate(
        [question for _, exact, synonym in CORPUS for question in (exact, synonym)] + NEGATIVES
    ):
        expected = relevant[file_ids[index // 2]] if index < 2 * len(CORPUS) else set()
        start = time.monotonic()
        try:
            result = await RetrievalService(sessions, settings, owner, None, store).search(
                kb, RetrievalRequest(query=question, top_n=5)
            )
            retrieval_elapsed = (time.monotonic() - start) * 1000
            assert result.trace_complete
            if not expected:
                answer = await QwenAnswerProvider(settings).generate(
                    InputContext(
                        mode="materials",
                        question=question,
                        previous_questions=[],
                        evidence=result.evidence,
                    )
                )
                generated_refusals.append(answer.refused and not answer.citation_ids)
            async with sessions() as session:
                trace = await session.get(RetrievalTrace, result.trace_id)
            stages = {stage["stage"]: stage for stage in trace.stages}
            for mode, stage_name in (
                ("FTS-only", "keyword"),
                ("Vector-only", "vector"),
                ("Hybrid-only", "fusion"),
                ("No-Rerank", "fusion"),
                ("Full", "rerank"),
            ):
                candidates = stages[stage_name]["candidates"]
                if mode == "Full":
                    ids = [str(e.chunk_id) for e in result.evidence]
                    elapsed = retrieval_elapsed
                else:
                    ids = [c["chunk_id"] for c in candidates][:5]
                    # 消融为同次 trace 候选离线重放；时间是阶段和，非独立负载测量。
                    elapsed = sum(
                        stages[name]["elapsed_ms"]
                        for name in (
                            {
                                "FTS-only": ["keyword"],
                                "Vector-only": ["query_embedding", "vector"],
                                "Hybrid-only": ["query_embedding", "keyword", "vector", "fusion"],
                                "No-Rerank": ["query_embedding", "keyword", "vector", "fusion"],
                            }[mode]
                        )
                    )
                if expected:
                    metrics[mode].append(ranking_metrics(ids, expected))
                else:
                    no_answer[mode].append(not ids)
                latencies[mode].append(elapsed)
            locations.extend(
                bool(e.page_start or e.paragraph_start) and bool(e.file_name)
                for e in result.evidence
            )
        except Exception:
            errors.append(index)
    report = [
        "# 合成中文检索评测",
        "",
        f"时间：{datetime.now(UTC).isoformat()}；8 份 TXT、16 个精确/同义问题、3 个无答案问题。",
        "",
        f"Embedding={settings.document_embedding_model}；Rerank={settings.document_rerank_model}；"
        f"策略 fts-jieba-or/vector/llama-rrf/qwen-rerank-v2；"
        f"门禁 {settings.document_retrieval_min_score}。",
        "",
        "| 策略 | Recall@5 | MRR@5 | nDCG@5 | 无答案正确率 | P95 ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, results in metrics.items():

        def average(name, samples=results):
            return sum(item[name] for item in samples) / len(samples) if samples else 0

        report.append(
            f"| {mode} | {average('recall'):.3f} | {average('mrr'):.3f} | "
            f"{average('ndcg'):.3f} | "
            f"{sum(no_answer[mode]) / len(no_answer[mode]) if no_answer[mode] else 0:.3f} | "
            f"{percentile95(latencies[mode]):.0f} |"
        )
    report += [
        "",
        f"来源定位完整率：{sum(locations) / len(locations) if locations else 0:.3f}；"
        f"错误率：{len(errors) / 19:.3f}。失败 query index：{errors}。",
        "",
        "关键词是 PostgreSQL FTS/ts_rank_cd，未实现 BM25，"
        "不能标为 BM25-only。Hybrid-only 与 No-Rerank 在"
        "本策略中相同。FTS/Vector/Hybrid 消融是同一 Trace 已授权"
        "候选的离线排序重放；其 P95 为阶段耗时和，不是独立并发压测或因果结论。未经过"
        "证据门禁的消融策略无答案率仅作对照。",
        "",
        "仅证明该小型合成集，不代表生产分布、四格式解析质量、恢复演练或用户原件人工验收。跨用户与撤权由独立集成测试验证。",
    ]
    target = REPO_ROOT / "openspec/changes/implement-learning-quick-answer/retrieval-evaluation.md"
    report.append(
        f"生成模型 qwen3.8-flash：合成无答案拒答 "
        f"{sum(generated_refusals)}/{len(generated_refusals)}；仅验证此三个样例。"
    )
    await asyncio.to_thread(target.write_text, "\n".join(report) + "\n")
    assert not errors
    assert len(metrics["Full"]) == 16
    assert sum(m["recall"] for m in metrics["Full"]) / 16 >= 0.9
    assert all(locations)
    assert len(generated_refusals) == 3 and all(generated_refusals)
