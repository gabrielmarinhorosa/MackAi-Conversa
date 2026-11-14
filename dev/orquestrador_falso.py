"""Orquestrador falso para desenvolver o Conversas sem depender do mackai-orquestrador.

Implementa o mesmo contrato (POST /v1/answers e GET /v1/status). Não chama o Gemini.

    uvicorn dev.orquestrador_falso:app --port 8001

Truques para testar o front:
- pergunta contendo "geral"  -> grounded=false, sem fontes
- pergunta contendo "lento"  -> demora 65 s (o Conversas devolve 503 por timeout)
- pergunta contendo "falha"  -> responde 500 (o Conversas devolve 503)
"""

import asyncio
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="mackai-orquestrador (falso)")


class Item(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class Pedido(BaseModel):
    question: str = Field(min_length=1, max_length=20000)
    profile: Literal["Desenvolvedor", "Product Owner", "Gerente de Projetos"]
    temperature: float = Field(ge=0, le=1)
    history: list[Item] = Field(max_length=10)
    project_id: str | None = None  # projeto do Módulo 1; ausente nas conversas gerais


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/status")
async def status():
    return {
        "llm": "offline",
        "model": "falso",
        "busca": {"strategy": "tfidf", "documents": 3, "chunks": 12,
                  "indexed_at": datetime.now(timezone.utc).isoformat()},
    }


@app.post("/v1/answers")
async def answers(pedido: Pedido):
    texto = pedido.question.lower()
    if "falha" in texto:
        raise HTTPException(500, "falha simulada")
    if "lento" in texto:
        await asyncio.sleep(65)

    geral = "geral" in texto
    conteudo = (
        f"**Resposta simulada** para o perfil *{pedido.profile}* "
        f"(temperatura {pedido.temperature:.1f}, {len(pedido.history)} mensagens de histórico, "
        f"projeto {pedido.project_id or 'nenhum'}).\n\n"
        "| Item | Valor |\n|---|---|\n| Pergunta | " + pedido.question[:80].replace("|", "/") + " |\n\n"
        "```python\nasync def exemplo() -> str:\n    return \"olá\"\n```"
    )
    fontes = [] if geral else [{
        "source": "modulo-7",
        "path": "services/busca/busca_semantica/rotas.py",
        "start_line": 1,
        "end_line": 30,
        "similarity": 0.82,
        "excerpt": "@router.post(\"/v1/search\")\nasync def buscar(pedido: PedidoBusca): ...",
    }]
    return {"content": conteudo, "mode": "offline", "grounded": not geral, "sources": fontes,
            "model": None, "usage": None}
