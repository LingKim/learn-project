import logging
import re

import jieba  # type: ignore[import-untyped]

jieba.setLogLevel(logging.ERROR)


def tokenize(value: str) -> str:
    # 中文词语进入 PostgreSQL simple tsvector；英文大小写由 PG 归一化。
    return " ".join(
        part for part in jieba.cut(value, HMM=False) if re.search(r"[\w\u4e00-\u9fff]", part)
    )
