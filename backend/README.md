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

## API 响应约定

业务 JSON 路由必须显式声明统一响应模型，响应体 `code` 与真实 HTTP 状态码保持一致：

```python
from fastapi import APIRouter
from pydantic import BaseModel

from xuemian_ai.core.errors import NotFoundError
from xuemian_ai.core.responses import ApiResponse, success_response
from xuemian_ai.core.status_codes import ApiStatusCode

router = APIRouter()


class UserResponse(BaseModel):
    id: int
    name: str


@router.get("/users/{user_id}", response_model=ApiResponse[UserResponse])
async def get_user(user_id: int) -> ApiResponse[UserResponse]:
    if user_id != 1:
        raise NotFoundError("用户不存在", error_key="USER_NOT_FOUND")
    return success_response(UserResponse(id=1, name="示例用户"))


@router.post(
    "/users",
    response_model=ApiResponse[UserResponse],
    status_code=ApiStatusCode.CREATED.value,
)
async def create_user() -> ApiResponse[UserResponse]:
    return success_response(
        UserResponse(id=1, name="示例用户"),
        message="创建成功",
        code=ApiStatusCode.CREATED,
    )
```

分页路由使用 `PageResponse[T]` 与 `page_response()`。HTTP 204、文件和流式响应不套统一响应体；健康检查保持裸响应。业务代码抛项目异常，不直接抛 FastAPI `HTTPException`。
