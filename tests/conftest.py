"""Testes com PostgreSQL de verdade e Orquestrador e Módulo 1 falsos (httpx.MockTransport).

Defina TEST_DATABASE_URL apontando para um banco descartável (as tabelas são truncadas a cada teste):

    TEST_DATABASE_URL=postgresql://mackai:mackai@localhost:5432/conversas_test pytest
"""

import asyncio
import json
import os
import time
import uuid

import asyncpg
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.exit("Defina TEST_DATABASE_URL (banco descartável) para rodar os testes.", returncode=2)

ISSUER = "mod1-auth-teste"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["MOD1_AUTH_URL"] = "http://mod1-auth"
os.environ["MOD1_PROJECTS_URL"] = "http://mod1-projects"
os.environ["MOD1_JWT_ISSUER"] = ISSUER

from fastapi.testclient import TestClient  # noqa: E402

from assistente_conversacional.main import criar_app  # noqa: E402
from assistente_conversacional.repositorio import SCHEMA  # noqa: E402

RESPOSTA_PADRAO = {
    "content": "Resposta **markdown**",
    "mode": "gemini",
    "grounded": True,
    "sources": [{
        "source": "modulo-7",
        "path": "services/busca/busca_semantica/rotas.py",
        "start_line": 1,
        "end_line": 30,
        "similarity": 0.82,
        "excerpt": "trecho",
    }],
    "model": "gemini-2.5-flash",
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


class OrquestradorFalso:
    """Faz o papel do mackai-orquestrador e guarda o que recebeu."""

    def __init__(self):
        self.pedidos: list[dict] = []
        self.cabecalhos: list[httpx.Headers] = []
        self.modo = "ok"  # ok | timeout | erro
        self.status_modo = "ok"  # ok | sem_busca | fora
        self.resposta = dict(RESPOSTA_PADRAO)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/status":
            if self.status_modo == "fora":
                raise httpx.ConnectError("fora do ar", request=request)
            busca = None if self.status_modo == "sem_busca" else {
                "strategy": "embedding", "documents": 42, "chunks": 380, "indexed_at": "2026-11-12T10:00:00Z"}
            return httpx.Response(200, json={"llm": "gemini", "model": "gemini-2.5-flash", "busca": busca})

        self.pedidos.append(json.loads(request.content))
        self.cabecalhos.append(request.headers)
        if self.modo == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if self.modo == "erro":
            return httpx.Response(500, json={"detail": "erro"})
        return httpx.Response(200, json=self.resposta)


CHAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "chave-de-teste"
JWK = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(CHAVE.public_key())), "kid": KID, "alg": "RS256", "use": "sig"}
LEITURA = ["backlog:read", "project:members:read", "project:read"]


class Modulo1Falso:
    """Faz o papel da Identidade e de Projetos do Módulo 1 e conta as chamadas."""

    def __init__(self):
        self.chamadas: list[str] = []
        self.revogados: set[str] = set()  # usuários com sessão encerrada (/auth/me -> 401)
        self.acessos: dict[tuple[str, str], list[str]] = {}  # (usuário, projeto) -> permissões
        self.fora = False

    def emitir(self, usuario: str | None = None, **claims) -> str:
        agora = int(time.time())
        payload = {"sub": usuario or str(uuid.uuid4()), "iss": ISSUER, "aud": "engenharia-software-api",
                   "iat": agora, "exp": agora + 1800, "jti": str(uuid.uuid4()), **claims}
        return jwt.encode(payload, CHAVE, algorithm="RS256", headers={"kid": KID, "typ": "JWT"})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.chamadas.append(request.url.path)
        if self.fora:
            raise httpx.ConnectError("fora do ar", request=request)
        if request.url.path == "/.well-known/jwks.json":
            return httpx.Response(200, json={"keys": [JWK]})
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        usuario = jwt.decode(token, options={"verify_signature": False})["sub"]
        if usuario in self.revogados:
            return httpx.Response(401, json={"detail": "Invalid authentication credentials"})
        if request.url.path == "/auth/me":
            return httpx.Response(200, json={"id": usuario, "email": "pessoa@exemplo.com", "display_name": "Pessoa",
                                             "is_active": True, "created_at": "2026-11-01T00:00:00Z"})
        partes = request.url.path.split("/")  # ["", "projects", id, "access", "v2"]
        if request.url.host == "mod1-projects" and partes[3:] == ["access", "v2"]:
            permissoes = self.acessos.get((usuario, partes[2]))
            if permissoes is None:
                return httpx.Response(404, json={"detail": "Project not found"})
            return httpx.Response(200, json={"project_id": partes[2], "user_id": usuario, "is_owner": False,
                                             "roles": ["developer"], "permissions": permissoes})
        return httpx.Response(404)


async def _limpar_banco():
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        await conn.execute(SCHEMA)
        await conn.execute("TRUNCATE conversations CASCADE")
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
def banco_limpo():
    asyncio.run(_limpar_banco())


@pytest.fixture
def orquestrador():
    return OrquestradorFalso()


@pytest.fixture
def modulo1():
    return Modulo1Falso()


@pytest.fixture
def novo_cliente(orquestrador, modulo1):
    """Fábrica: cada chamada sobe um app novo (equivale a reiniciar o serviço) com o mesmo banco."""
    abertos = []

    def fabricar() -> TestClient:
        cliente = TestClient(criar_app(httpx.MockTransport(orquestrador), httpx.MockTransport(modulo1)))
        cliente.__enter__()
        abertos.append(cliente)
        return cliente

    yield fabricar
    for cliente in abertos:
        cliente.__exit__(None, None, None)


@pytest.fixture
def client(novo_cliente):
    return novo_cliente()


def token(modulo1: Modulo1Falso, usuario: str | None = None) -> dict:
    """Emite um JWT do Módulo 1 (um usuário novo, se não informado) e devolve o cabeçalho Authorization."""
    return {"Authorization": f"Bearer {modulo1.emitir(usuario)}"}


def usuario_de(auth: dict) -> str:
    return jwt.decode(auth["Authorization"].removeprefix("Bearer "), options={"verify_signature": False})["sub"]


def perguntar(client: TestClient, auth: dict, mensagem: str = "Como funciona a busca?", **extra):
    return client.post("/api/chat", headers=auth, json={"message": mensagem, **extra})

