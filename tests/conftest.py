"""Testes com PostgreSQL de verdade e Orquestrador falso (httpx.MockTransport).

Defina TEST_DATABASE_URL apontando para um banco descartável (as tabelas são truncadas a cada teste):

    TEST_DATABASE_URL=postgresql://mackai:mackai@localhost:5432/conversas_test pytest
"""

import asyncio
import json
import os

import asyncpg
import httpx
import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.exit("Defina TEST_DATABASE_URL (banco descartável) para rodar os testes.", returncode=2)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SESSION_SECRET"] = "segredo-de-teste-com-mais-de-32-caracteres"

from fastapi.testclient import TestClient  # noqa: E402

from assistente_conversacional import config  # noqa: E402
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
def novo_cliente(orquestrador):
    """Fábrica: cada chamada sobe um app novo (equivale a reiniciar o serviço) com o mesmo banco."""
    abertos = []

    def fabricar() -> TestClient:
        cliente = TestClient(criar_app(httpx.MockTransport(orquestrador)))
        cliente.__enter__()
        abertos.append(cliente)
        return cliente

    yield fabricar
    for cliente in abertos:
        cliente.__exit__(None, None, None)


@pytest.fixture
def client(novo_cliente):
    return novo_cliente()


def token(client: TestClient, ip: str = "10.0.0.1") -> dict:
    """Cria uma sessão e devolve o cabeçalho Authorization pronto."""
    resposta = client.post("/api/sessions", headers={"X-Forwarded-For": ip})
    assert resposta.status_code == 200, resposta.text
    return {"Authorization": f"Bearer {resposta.json()['token']}"}


def perguntar(client: TestClient, auth: dict, mensagem: str = "Como funciona a busca?", **extra):
    return client.post("/api/chat", headers=auth, json={"message": mensagem, **extra})

