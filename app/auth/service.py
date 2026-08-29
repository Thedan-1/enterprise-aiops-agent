"""Small, dependency-free auth service used by the DB-free demo.

This is intentionally not presented as an enterprise identity provider.  It gives the
demo a real, testable security boundary while keeping the production migration path
clear: replace this module with OIDC and keep AuthContext/RBAC contracts unchanged.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    tenant_id: str
    role: str


DEMO_USERS = {
    "operator@alpha": {"password": "AlphaDemo!2026", "tenant_id": "alpha", "role": "operator"},
    "viewer@alpha": {"password": "ViewerDemo!2026", "tenant_id": "alpha", "role": "viewer"},
    "auditor@alpha": {"password": "AuditDemo!2026", "tenant_id": "alpha", "role": "auditor"},
    "operator@beta": {"password": "BetaDemo!2026", "tenant_id": "beta", "role": "operator"},
}


class AuthError(ValueError):
    pass


class AuthService:
    def __init__(self, secret: str | None = None, ttl_s: int = 3600):
        # No public fallback secret: when AUTH_SECRET is absent the demo gets a fresh
        # process-local secret, so cloning the repository does not reveal a signing key.
        self.secret = (secret or os.getenv("AUTH_SECRET") or secrets.token_urlsafe(32)).encode()
        self.ttl_s = ttl_s

    def login(self, username: str, password: str) -> str:
        record = DEMO_USERS.get(username)
        if not record or not hmac.compare_digest(record["password"], password):
            raise AuthError("用户名或密码错误")
        payload = {
            "sub": username,
            "tenant": record["tenant_id"],
            "role": record["role"],
            "exp": int(time.time()) + self.ttl_s,
        }
        body = self._b64(json.dumps(payload, separators=(",", ":")).encode())
        signature = self._b64(hmac.new(self.secret, body.encode(), hashlib.sha256).digest())
        return f"{body}.{signature}"

    def verify(self, token: str) -> AuthContext:
        try:
            body, signature = token.split(".", 1)
            expected = self._b64(hmac.new(self.secret, body.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected):
                raise AuthError("Token 签名无效")
            payload = json.loads(self._unb64(body))
            if int(payload["exp"]) <= int(time.time()):
                raise AuthError("Token 已过期")
            return AuthContext(payload["sub"], payload["tenant"], payload["role"])
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            if isinstance(exc, AuthError):
                raise
            raise AuthError("Token 格式无效") from exc

    @staticmethod
    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    @staticmethod
    def _unb64(value: str) -> str:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
