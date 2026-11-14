"""Módulo 1 falso (Identidade + Projetos) para desenvolver o Conversas sem conta no Módulo 1 real.

Implementa só o que o Conversas e o front usam, no mesmo contrato do Módulo 1 (release 0.5.0):
POST /auth/token, POST /auth/mfa/verify, POST /auth/refresh, POST /auth/logout, GET /auth/me,
GET /.well-known/jwks.json, GET /projects e GET /projects/{id}/access/v2.

    uvicorn dev.modulo1_falso:app --port 8002

Qualquer e-mail e senha entram (o id do usuário é derivado do e-mail). E-mail começando com "mfa"
pede o código 123456. A chave RSA é gerada a cada início: tokens antigos deixam de valer.
Configure o Conversas com MOD1_AUTH_URL=MOD1_PROJECTS_URL=http://localhost:8002 e
MOD1_JWT_ISSUER=mod1-auth-local.
"""

import json
import os
import time
import uuid
from urllib.parse import parse_qs

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

ISSUER = "mod1-auth-local"
AUDIENCE = "engenharia-software-api"
KID = "chave-local"
TTL_S = int(os.getenv("MOD1_FALSO_TTL_S", "1800"))
CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(CHAVE.public_key())), "kid": KID, "alg": "RS256", "use": "sig"}

PROJETOS = [
    {"id": "7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01", "name": "MackAI — Módulo 7", "description": "Assistente RAG"},
    {"id": "7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a02", "name": "Portal de Notificações", "description": "Módulo 6"},
]
PERMISSOES = ["backlog:read", "project:members:read", "project:read"]

usuarios: dict[str, dict] = {}  # id -> {email, display_name}
refresh_tokens: dict[str, str] = {}  # refresh -> id do usuário
desafios: dict[str, str] = {}  # challenge_token -> id do usuário
encerrados: set[str] = set()  # jti de sessões encerradas por logout

app = FastAPI(title="Módulo 1 (falso)")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:8000"],
                   allow_methods=["*"], allow_headers=["*"])


def emitir(usuario: str) -> dict:
    agora = int(time.time())
    access = jwt.encode({"sub": usuario, "iss": ISSUER, "aud": AUDIENCE, "iat": agora, "exp": agora + TTL_S,
                         "jti": str(uuid.uuid4()), "sid": str(uuid.uuid4())},
                        CHAVE, algorithm="RS256", headers={"kid": KID, "typ": "JWT"})
    refresh = uuid.uuid4().hex
    refresh_tokens[refresh] = usuario
    return {"access_token": access, "token_type": "bearer", "expires_in": TTL_S, "refresh_token": refresh}


def usuario_do_token(request: Request) -> str:
    try:
        claims = jwt.decode(request.headers.get("Authorization", "").removeprefix("Bearer "), CHAVE.public_key(),
                            algorithms=["RS256"], issuer=ISSUER, audience=AUDIENCE)
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid authentication credentials", headers={"WWW-Authenticate": "Bearer"})
    if claims["jti"] in encerrados or claims["sub"] not in usuarios:
        raise HTTPException(401, "Invalid authentication credentials", headers={"WWW-Authenticate": "Bearer"})
    return claims["sub"]


@app.get("/health/ready")
async def ready():
    return {"status": "ready"}


@app.get("/.well-known/jwks.json")
async def jwks():
    return {"keys": [JWK]}


@app.post("/auth/token")
async def token(request: Request):
    # Formulário application/x-www-form-urlencoded, como no Módulo 1 (sem depender de python-multipart).
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    email, senha = form.get("username", "").strip().lower(), form.get("password", "")
    if not email or not senha:
        raise HTTPException(401, "Invalid credentials")
    usuario = str(uuid.uuid5(uuid.NAMESPACE_URL, "mod1-falso:" + email))
    usuarios[usuario] = {"email": email, "display_name": email.split("@")[0].replace(".", " ").title()}
    if email.startswith("mfa"):
        desafio = uuid.uuid4().hex
        desafios[desafio] = usuario
        return {"mfa_required": True, "challenge_token": desafio, "expires_in": 300}
    return emitir(usuario)


@app.post("/auth/mfa/verify")
async def verificar_mfa(corpo: dict):
    usuario = desafios.get(corpo.get("challenge_token", ""))
    if usuario is None or corpo.get("code") != "123456":
        raise HTTPException(401, "Invalid MFA challenge")
    del desafios[corpo["challenge_token"]]
    return emitir(usuario)


@app.post("/auth/refresh")
async def refresh(corpo: dict):
    usuario = refresh_tokens.pop(corpo.get("refresh_token", ""), None)
    if usuario is None:
        raise HTTPException(401, "Invalid refresh token")
    return emitir(usuario)


@app.post("/auth/logout", status_code=204)
async def logout(request: Request):
    usuario_do_token(request)
    claims = jwt.decode(request.headers["Authorization"].removeprefix("Bearer "), options={"verify_signature": False})
    encerrados.add(claims["jti"])
    return Response(status_code=204)


@app.get("/auth/me")
async def me(request: Request):
    usuario = usuario_do_token(request)
    return {"id": usuario, **usuarios[usuario], "is_active": True, "created_at": "2026-11-01T00:00:00Z",
            "is_admin": False, "email_verified": True}


@app.get("/projects")
async def projetos(request: Request, limit: int = 20, offset: int = 0):
    usuario = usuario_do_token(request)
    itens = [{**p, "owner_id": usuario, "status": "active", "archived": False} for p in PROJETOS]
    return {"items": itens[offset:offset + limit], "total": len(itens), "limit": limit, "offset": offset}


@app.get("/projects/{project_id}/access/v2")
async def acesso(project_id: str, request: Request):
    usuario = usuario_do_token(request)
    if project_id not in {p["id"] for p in PROJETOS}:
        raise HTTPException(404, "Project not found")
    return {"project_id": project_id, "user_id": usuario, "is_owner": True, "roles": ["owner"],
            "permissions": PERMISSOES, "access_version": 2}
