import os
import time
import logging
from typing import Dict, Any

import requests
from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError


logger = logging.getLogger(__name__)


class OIDCConfig:
    issuer: str
    audience: str
    jwks_url: str

    def __init__(self) -> None:
        self.issuer = os.getenv("OIDC_ISSUER", "")
        self.audience = os.getenv("OIDC_AUDIENCE", "")
        self.jwks_url = os.getenv("OIDC_JWKS_URL", "")


_oidc_config = OIDCConfig()
_jwks_cache: Dict[str, Any] = {"keys": [], "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 3600


def _get_jwks() -> Dict[str, Any]:
    now = time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < _JWKS_TTL_SECONDS:
        return {"keys": _jwks_cache["keys"]}

    if not _oidc_config.jwks_url:
        raise RuntimeError("OIDC_JWKS_URL is not configured")

    resp = requests.get(_oidc_config.jwks_url, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    _jwks_cache["keys"] = data.get("keys", [])
    _jwks_cache["fetched_at"] = now
    return {"keys": _jwks_cache["keys"]}


def verify_jwt(token: str) -> Dict[str, Any]:
    """Verify a JWT access/id token from the OIDC provider.

    Stateless: we only use public JWKS and config; no per-user storage.
    """
    if not token:
        raise JWTError("Empty token")

    jwks = _get_jwks()

    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256", "ES256", "PS256"],
            audience=_oidc_config.audience or None,
            issuer=_oidc_config.issuer or None,
            options={"verify_aud": bool(_oidc_config.audience)},
        )
        return claims
    except ExpiredSignatureError as exc:
        logger.warning("JWT expired: %s", exc)
        raise
    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise
