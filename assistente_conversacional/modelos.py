"""Modelos Pydantic: o contrato público de /api/* e o contrato consumido do Orquestrador."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from . import config

Perfil = Literal["Desenvolvedor", "Product Owner", "Gerente de Projetos"]
Papel = Literal["user", "assistant"]
Voto = Literal["up", "down"]

TextoPergunta = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=config.MAX_MESSAGE_CHARS)
]


# ---------- Contrato público (/api/*) ----------

class Saude(BaseModel):
    status: Literal["ok", "degraded"]
    llm: str = Field(description="`gemini`, `offline` ou outro valor repassado pelo Orquestrador.")
    documents: int
    chunks: int
    indexed_at: datetime | None


class ResumoConversa(BaseModel):
    id: UUID
    project_id: UUID | None = Field(description="Projeto do Módulo 1. Nulo = conversa geral.")
    title: str
    created_at: datetime


class PedidoConversa(BaseModel):
    project_id: UUID | None = Field(None, description="Projeto do Módulo 1. Exige acesso de leitura ao projeto.")


class Fonte(BaseModel):
    source: str = Field(description="Módulo de origem do trecho, por exemplo `modulo-7`.")
    path: str
    start_line: int
    end_line: int
    similarity: float
    excerpt: str


class Mensagem(BaseModel):
    id: UUID
    role: Papel
    content: str
    sources: list[Fonte] = []
    grounded: bool | None = Field(None, description="`false` quando a resposta não veio dos arquivos do projeto.")
    mode: str | None = Field(None, description="`gemini`, `offline` ou `fallback`. Nulo nas mensagens do usuário.")
    feedback: Voto | None = None
    created_at: datetime


class ConversaDetalhada(ResumoConversa):
    messages: list[Mensagem]


class PedidoChat(BaseModel):
    message: TextoPergunta
    conversation_id: UUID | None = Field(None, description="Nulo cria uma conversa nova.")
    project_id: UUID | None = Field(
        None, description="Projeto do Módulo 1 da conversa nova. Ignorado quando `conversation_id` é enviado: "
                          "vale o projeto da conversa.")
    profile: Perfil = "Desenvolvedor"
    temperature: float = Field(0.4, ge=0, le=1)

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "message": "Como funciona a busca?",
                "conversation_id": None,
                "project_id": None,
                "profile": "Desenvolvedor",
                "temperature": 0.4,
            }]
        }
    }


class RespostaChat(BaseModel):
    conversation_id: UUID
    message: Mensagem


class PedidoFeedback(BaseModel):
    message_id: UUID
    value: Voto | None = Field(description="`null` remove o voto.")


class MetricasProjeto(BaseModel):
    project_id: UUID
    conversations: int = Field(description="Conversas com pelo menos uma pergunta.")
    users: int = Field(description="Pessoas diferentes que perguntaram.")
    questions: int
    answers_up: int = Field(description="Respostas votadas como úteis.")
    answers_down: int = Field(description="Respostas votadas como não úteis.")
    answers_not_grounded: int = Field(description="Respostas que não vieram dos arquivos do projeto.")
    last_question_at: datetime | None


class Ok(BaseModel):
    ok: bool = True


class Erro(BaseModel):
    detail: str
    code: str


# ---------- Contrato do Orquestrador (POST /v1/answers, GET /v1/status) ----------

class ItemHistorico(BaseModel):
    role: Papel
    content: str


class PedidoResposta(BaseModel):
    question: str
    profile: Perfil
    temperature: float
    history: list[ItemHistorico]
    project_id: UUID | None = None  # só é enviado quando a conversa tem projeto


class RespostaOrquestrador(BaseModel):
    content: str
    mode: str
    grounded: bool
    sources: list[Fonte] = []
    model: str | None = None
    usage: dict | None = None
