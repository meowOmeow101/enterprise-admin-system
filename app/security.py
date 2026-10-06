"""
密码哈希与 JWT 令牌。

密码哈希用标准库 hashlib 的 PBKDF2-HMAC-SHA256 手写实现：
不引入 passlib/bcrypt 这类需要编译的依赖，Windows 上装起来零风险，
安全性（20 万次迭代 + 每用户随机盐）对本系统足够。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from .config import JWT_ALGORITHM, SECRET_KEY, TOKEN_EXPIRE_MINUTES

_ITERATIONS = 200_000
_ALGO = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """返回 `pbkdf2_sha256$迭代次数$盐$哈希` 格式的字符串。"""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "{}${}${}${}".format(
        _ALGO,
        _ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    """校验密码，使用恒定时间比较避免时序攻击。"""
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def create_access_token(subject: str, extra: dict | None = None) -> str:
    """签发 JWT。subject 用用户 id。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """解析并校验 JWT，失败返回 None。"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
