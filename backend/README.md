# 学面通AI后端

FastAPI 模块化单体脚手架。当前只包含系统健康纵切，不包含 PRD 业务模块。

## 常用命令

```bash
uv sync
uv run uvicorn xuemian_ai.main:app --reload
uv run ruff check .
uv run mypy
uv run pytest
uv run python -m xuemian_ai.openapi ../openapi/openapi.json
```
