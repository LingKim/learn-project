from pydantic import BaseModel, Field

from xuemian_ai.core.status_codes import ApiStatusCode


class ApiResponse[T](BaseModel):
    code: int
    message: str
    data: T


class PageMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PageResponse[T](BaseModel):
    code: int
    message: str
    data: list[T]
    meta: PageMeta


def success_response[T](
    data: T,
    *,
    message: str = "请求成功",
    code: ApiStatusCode = ApiStatusCode.OK,
) -> ApiResponse[T]:
    if code not in {ApiStatusCode.OK, ApiStatusCode.CREATED}:
        raise ValueError("success response code must be 200 or 201")
    return ApiResponse(code=code.value, message=message, data=data)


def page_response[T](
    data: list[T],
    *,
    page: int,
    page_size: int,
    total: int,
    message: str = "查询成功",
) -> PageResponse[T]:
    if page < 1:
        raise ValueError("page must be greater than or equal to 1")
    if page_size < 1:
        raise ValueError("page_size must be greater than or equal to 1")
    if total < 0:
        raise ValueError("total must be greater than or equal to 0")
    total_pages = (total + page_size - 1) // page_size
    return PageResponse(
        code=ApiStatusCode.OK.value,
        message=message,
        data=data,
        meta=PageMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        ),
    )
