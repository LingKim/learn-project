"""固定评测指标；排序来源与因果贡献不混淆。"""

import math


def ranking_metrics(ranked: list[str], relevant: set[str], k: int = 5) -> dict[str, float]:
    if not relevant:
        return {"recall": 0.0, "mrr": 0.0, "ndcg": 0.0}
    ranked = list(dict.fromkeys(ranked))[:k]
    hits = [i + 1 for i, identifier in enumerate(ranked) if identifier in relevant]
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return {
        "recall": len(hits) / len(relevant),
        "mrr": 1 / hits[0] if hits else 0.0,
        "ndcg": sum(1 / math.log2(rank + 1) for rank in hits) / ideal,
    }


def percentile95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(len(values) * 0.95) - 1)] if values else 0.0
