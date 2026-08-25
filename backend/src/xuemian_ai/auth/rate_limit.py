from time import time
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from xuemian_ai.core.errors import TooManyRequestsError, UpstreamServiceError
from xuemian_ai.core.status_codes import ApiStatusCode

_WINDOW_SECONDS = 15 * 60
_LOCK_SECONDS = 15 * 60
_ACCOUNT_LIMIT = 5
_IP_LIMIT = 20

_RECORD_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = now - tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
redis.call('ZADD', key, now, ARGV[3])
redis.call('EXPIRE', key, tonumber(ARGV[4]))
return redis.call('ZCARD', key)
"""

_COUNT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = now - tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
return redis.call('ZCARD', key)
"""


class AuthRateLimiter:
    def __init__(self, redis: Redis, prefix: str) -> None:
        self._redis = redis
        self._prefix = prefix

    async def ensure_login_allowed(self, username_key: str, ip_key: str) -> None:
        account_count = await self._count(self._key("login:account", username_key))
        ip_count = await self._count(self._key("login:ip", ip_key))
        if account_count >= _ACCOUNT_LIMIT or ip_count >= _IP_LIMIT:
            raise TooManyRequestsError(retry_after=_LOCK_SECONDS, error_key="AUTH_RATE_LIMITED")

    async def record_login_failure(self, username_key: str, ip_key: str) -> None:
        account_count = await self._record(self._key("login:account", username_key))
        ip_count = await self._record(self._key("login:ip", ip_key))
        if account_count >= _ACCOUNT_LIMIT or ip_count >= _IP_LIMIT:
            raise TooManyRequestsError(retry_after=_LOCK_SECONDS, error_key="AUTH_RATE_LIMITED")

    async def clear_login_account(self, username_key: str) -> None:
        try:
            await self._redis.delete(self._key("login:account", username_key))
        except RedisError as exc:
            raise self._unavailable() from exc

    async def record_registration_attempt(self, ip_key: str) -> None:
        count = await self._record(self._key("register:ip", ip_key))
        if count > _IP_LIMIT:
            raise TooManyRequestsError(retry_after=_LOCK_SECONDS, error_key="AUTH_RATE_LIMITED")

    def _key(self, namespace: str, identity: str) -> str:
        return f"{self._prefix}:{namespace}:{identity}"

    async def _count(self, key: str) -> int:
        now_ms = int(time() * 1000)
        try:
            result = await self._redis.eval(
                _COUNT_SCRIPT,
                1,
                key,
                now_ms,
                _WINDOW_SECONDS * 1000,
            )
            return int(result)
        except RedisError as exc:
            raise self._unavailable() from exc

    async def _record(self, key: str) -> int:
        now_ms = int(time() * 1000)
        try:
            result = await self._redis.eval(
                _RECORD_SCRIPT,
                1,
                key,
                now_ms,
                _WINDOW_SECONDS * 1000,
                str(uuid4()),
                _WINDOW_SECONDS + _LOCK_SECONDS,
            )
            return int(result)
        except RedisError as exc:
            raise self._unavailable() from exc

    @staticmethod
    def _unavailable() -> UpstreamServiceError:
        return UpstreamServiceError(
            "认证保护服务暂时不可用，请稍后重试",
            status_code=ApiStatusCode.SERVICE_UNAVAILABLE,
            error_key="AUTH_RATE_LIMIT_UNAVAILABLE",
        )
