# 合成中文检索评测

时间：2026-10-02T13:49:32.634287+00:00；8 份 TXT、16 个精确/同义问题、3 个无答案问题。

Embedding=qwen3.7-text-embedding；Rerank=qwen3-rerank；策略 fts-jieba/vector/llama-rrf/qwen-rerank-v1；门禁 0.2。

| 策略 | Recall@5 | MRR@5 | nDCG@5 | 无答案正确率 | P95 ms |
|---|---:|---:|---:|---:|---:|
| FTS-only | 0.000 | 0.000 | 0.000 | 1.000 | 33 |
| Vector-only | 1.000 | 1.000 | 1.000 | 0.000 | 529 |
| Hybrid-only | 1.000 | 1.000 | 1.000 | 0.000 | 546 |
| No-Rerank | 1.000 | 1.000 | 1.000 | 0.000 | 546 |
| Full | 1.000 | 1.000 | 1.000 | 0.000 | 871 |

来源定位完整率：1.000；错误率：0.000。失败 query index：[]。

关键词是 PostgreSQL FTS/ts_rank_cd，未实现 BM25，不能标为 BM25-only。Hybrid-only 与 No-Rerank 在本策略中相同。FTS/Vector/Hybrid 消融是同一 Trace 已授权候选的离线排序重放；其 P95 为阶段耗时和，不是独立并发压测或因果结论。未经过证据门禁的消融策略无答案率仅作对照。

仅证明该小型合成集，不代表生产分布、四格式解析质量、恢复演练或用户原件人工验收。跨用户与撤权由独立集成测试验证。
