from collections.abc import Mapping

from xuemian_ai.core.status_codes import ApiStatusCode


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: ApiStatusCode = ApiStatusCode.INTERNAL_SERVER_ERROR,
        title: str = "请求失败",
        error_type: str = "about:blank",
        error_key: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.title = title
        self.error_type = error_type
        self.error_key = error_key
        self.headers = dict(headers) if headers is not None else None


class BadRequestError(AppError):
    def __init__(self, message: str = "请求参数错误", *, error_key: str | None = None) -> None:
        super().__init__(
            message,
            status_code=ApiStatusCode.BAD_REQUEST,
            title="请求参数错误",
            error_type="https://xuemian.ai/problems/bad-request",
            error_key=error_key,
        )


class UnauthorizedError(AppError):
    def __init__(
        self,
        message: str = "身份认证失败",
        *,
        error_key: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=ApiStatusCode.UNAUTHORIZED,
            title="身份认证失败",
            error_type="https://xuemian.ai/problems/unauthorized",
            error_key=error_key,
            headers=headers,
        )


class ForbiddenError(AppError):
    def __init__(self, message: str = "没有操作权限", *, error_key: str | None = None) -> None:
        super().__init__(
            message,
            status_code=ApiStatusCode.FORBIDDEN,
            title="禁止访问",
            error_type="https://xuemian.ai/problems/forbidden",
            error_key=error_key,
        )


class NotFoundError(AppError):
    def __init__(self, message: str = "请求的资源不存在", *, error_key: str | None = None) -> None:
        super().__init__(
            message,
            status_code=ApiStatusCode.NOT_FOUND,
            title="资源不存在",
            error_type="https://xuemian.ai/problems/resource-not-found",
            error_key=error_key,
        )


class ConflictError(AppError):
    def __init__(self, message: str = "资源状态冲突", *, error_key: str | None = None) -> None:
        super().__init__(
            message,
            status_code=ApiStatusCode.CONFLICT,
            title="资源冲突",
            error_type="https://xuemian.ai/problems/conflict",
            error_key=error_key,
        )


class ValidationAppError(AppError):
    def __init__(self, message: str = "请求参数不合法", *, error_key: str | None = None) -> None:
        super().__init__(
            message,
            status_code=ApiStatusCode.VALIDATION_ERROR,
            title="请求参数不合法",
            error_type="https://xuemian.ai/problems/validation-error",
            error_key=error_key,
        )


class TooManyRequestsError(AppError):
    def __init__(
        self,
        message: str = "请求过于频繁，请稍后重试",
        *,
        retry_after: int,
        error_key: str | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=ApiStatusCode.TOO_MANY_REQUESTS,
            title="请求过于频繁",
            error_type="https://xuemian.ai/problems/rate-limited",
            error_key=error_key,
            headers={"Retry-After": str(retry_after)},
        )


class UpstreamServiceError(AppError):
    def __init__(
        self,
        message: str = "上游服务暂时不可用",
        *,
        status_code: ApiStatusCode = ApiStatusCode.BAD_GATEWAY,
        error_key: str | None = None,
    ) -> None:
        allowed_statuses = {
            ApiStatusCode.BAD_GATEWAY,
            ApiStatusCode.SERVICE_UNAVAILABLE,
            ApiStatusCode.GATEWAY_TIMEOUT,
        }
        if status_code not in allowed_statuses:
            raise ValueError("upstream service status must be 502, 503 or 504")
        super().__init__(
            message,
            status_code=status_code,
            title="上游服务异常",
            error_type="https://xuemian.ai/problems/upstream-service-error",
            error_key=error_key,
        )
