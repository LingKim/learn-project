"""显式配置密钥环并绑定工单/授权身份，禁止明文或随机密钥降级。"""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from xuemian_ai.core.errors import UpstreamServiceError
from xuemian_ai.core.status_codes import ApiStatusCode


def unavailable() -> UpstreamServiceError:
    return UpstreamServiceError(
        "诊断加密服务不可用",
        status_code=ApiStatusCode.SERVICE_UNAVAILABLE,
        error_key="DIAGNOSTIC_CRYPTO_UNAVAILABLE",
    )


class SnapshotCipher:
    def __init__(self, settings: Any) -> None:
        try:
            raw = json.loads(settings.diagnostic_snapshot_keys.get_secret_value())
            self.active_key_id = settings.diagnostic_snapshot_active_key_id
            if not isinstance(raw, dict) or self.active_key_id not in raw:
                raise ValueError("missing key")
            self.keys = {name: Fernet(value.encode("ascii")) for name, value in raw.items()}
        except (ValueError, TypeError, AttributeError, UnicodeError):
            raise unavailable() from None

    def encrypt(self, scope: str, value: dict[str, Any]) -> tuple[str, str]:
        plaintext = json.dumps({"scope": scope, "value": value}, ensure_ascii=False).encode()
        return self.active_key_id, self.keys[self.active_key_id].encrypt(plaintext).decode("ascii")

    def decrypt(self, scope: str, key_id: str, ciphertext: str) -> dict[str, Any]:
        try:
            result = json.loads(self.keys[key_id].decrypt(ciphertext.encode("ascii")))
            if result["scope"] != scope or not isinstance(result["value"], dict):
                raise ValueError("wrong scope")
            return dict(result["value"])
        except (KeyError, ValueError, TypeError, InvalidToken, UnicodeError):
            raise unavailable() from None
