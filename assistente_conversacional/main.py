"""App FastAPI do mackai-conversas: handler de erros, X-Request-ID e montagem do front."""

import logging
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from . import config, repositorio
from .cliente_orquestrador import ClienteOrquestrador
from .erros import ErroApi
from .limites import Limites
from .rotas import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("mackai.conversas")

DESCRICAO = """
Porta de entrada pública do MackAI (Módulo 7): sessões anônimas, conversas, mensagens e feedback.
As perguntas são repassadas ao `mackai-orquestrador` (`POST /v1/answers`).

**Autenticação:** chame `POST /api/sessions`, guarde o `token` e envie `Authorization: Bearer <token>`
em todas as outras rotas `/api/*` (exceto `/api/health`).

**Erros:** `{"detail": "mensagem legível", "code": "CODIGO"}`. Validação continua no 422 padrão do FastAPI.

**Rastreamento:** envie `X-Request-ID` para correlacionar logs; se não enviar, o serviço gera um.
"""


def criar_app(orquestrador_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """`orquestrador_transport` existe para os testes trocarem o Orquestrador por um falso."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if len(config.SESSION_SECRET) < 32:
            raise RuntimeError("SESSION_SECRET precisa ter 32 ou mais caracteres.")
        app.state.pool = await repositorio.abrir_pool(config.DATABASE_URL)
        app.state.orquestrador = ClienteOrquestrador(
            config.ORQUESTRADOR_URL, config.ORQUESTRADOR_TIMEOUT_S, config.STATUS_TIMEOUT_S,
            transport=orquestrador_transport,
        )
        app.state.limites = Limites(config.CHAT_LIMIT_PER_USER, config.CHAT_LIMIT_GLOBAL,
                                    config.SESSION_LIMIT_PER_IP)
        yield
        await app.state.orquestrador.fechar()
        await app.state.pool.close()

    app = FastAPI(title="mackai-conversas", version="1.0.0", description=DESCRICAO, lifespan=lifespan)

    if config.CORS_ORIGINS:
        app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"],
                           allow_headers=["*"], expose_headers=["X-Request-ID"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ErroApi)
    async def erro_api(request: Request, erro: ErroApi):
        return JSONResponse({"detail": erro.detail, "code": erro.code}, status_code=erro.status)

    @app.exception_handler(HTTPException)
    async def erro_http(request: Request, erro: HTTPException):
        return JSONResponse({"detail": str(erro.detail), "code": f"HTTP_{erro.status_code}"},
                            status_code=erro.status_code, headers=erro.headers)

    @app.exception_handler(Exception)
    async def erro_inesperado(request: Request, erro: Exception):
        log.exception("request_id=%s erro inesperado", getattr(request.state, "request_id", "-"))
        return JSONResponse({"detail": "Erro interno.", "code": "ERRO_INTERNO"}, status_code=500)

    @app.get("/health", tags=["saúde"], summary="Sonda de vida e prontidão do Container Apps")
    async def health():
        return {"status": "ok"}

    app.include_router(router)

    # O front compilado fica por último para não cobrir /api e /health.
    if config.FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")

    return app


app = criar_app()
