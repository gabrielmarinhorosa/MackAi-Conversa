"""Sessão anônima: token JWT HS256 com `sub` = UUID do usuário (seção 7)."""

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config
from .erros import nao_autenticado

_bearer = HTTPBearer(auto_error=False, description="Token obtido em POST /api/sessions.")


def criar_token() -> tuple[str, datetime]:
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(days=config.SESSION_DAYS)
    payload = {"sub": str(uuid.uuid4()), "iat": agora, "exp": expira}
    return jwt.encode(payload, config.SESSION_SECRET, algorithm="HS256"), expira


def usuario_atual(credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> UUID:
    """Dependência das rotas protegidas. Devolve o UUID do dono do token ou 401."""
    if credenciais is None:
        raise nao_autenticado()
    try:
        payload = jwt.decode(credenciais.credentials, config.SESSION_SECRET, algorithms=["HS256"],
                             options={"require": ["sub", "exp"]})
        return UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        raise nao_autenticado()
