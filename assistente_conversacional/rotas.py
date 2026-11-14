"""Rotas públicas /api/*. Todas exigem token, exceto `sessions` e `health`."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from . import repositorio
from .cliente_orquestrador import OrquestradorIndisponivel
from .erros import (conversa_nao_encontrada, mensagem_nao_encontrada, muitas_requisicoes,
                    orquestrador_indisponivel)
from .limites import ip_do_cliente
from .modelos import (ConversaDetalhada, Erro, ItemHistorico, Ok, PedidoChat, PedidoFeedback,
                      PedidoResposta, RespostaChat, ResumoConversa, Saude, SessaoCriada)
from .sessoes import criar_token, usuario_atual

log = logging.getLogger("mackai.conversas")

router = APIRouter(prefix="/api")

E401 = {401: {"model": Erro, "description": "Token ausente ou inválido"}}
E404 = {404: {"model": Erro, "description": "Não existe ou é de outro dono"}}
E429 = {429: {"model": Erro, "description": "Limite de requisições por minuto"}}
E503 = {503: {"model": Erro, "description": "Orquestrador indisponível"}}


@router.post("/sessions", response_model=SessaoCriada, tags=["sessões"], responses=E429,
             summary="Cria uma sessão anônima")
async def criar_sessao(request: Request, x_forwarded_for: str | None = Header(None)):
    ip = ip_do_cliente(x_forwarded_for, request.client.host if request.client else None)
    if not request.app.state.limites.sessoes_ip.permitir(ip):
        raise muitas_requisicoes()
    token, expira = criar_token()
    return SessaoCriada(token=token, expires_at=expira)


@router.get("/health", response_model=Saude, tags=["saúde"],
            summary="Estado do serviço agregado com o do Orquestrador")
async def saude(request: Request):
    status = await request.app.state.orquestrador.status(request.state.request_id)
    if status is None:
        return Saude(status="degraded", llm="offline", documents=0, chunks=0, indexed_at=None)
    busca = status.get("busca") or {}
    return Saude(
        status="ok" if status.get("busca") else "degraded",
        llm=status.get("llm") or "offline",
        documents=busca.get("documents", 0),
        chunks=busca.get("chunks", 0),
        indexed_at=busca.get("indexed_at"),
    )


@router.get("/conversations", response_model=list[ResumoConversa], tags=["conversas"], responses=E401,
            summary="Lista as conversas do dono do token que têm mensagens")
async def listar_conversas(request: Request, dono: UUID = Depends(usuario_atual)):
    return await repositorio.listar_conversas(request.app.state.pool, dono)


@router.post("/conversations", response_model=ResumoConversa, status_code=201, tags=["conversas"],
             responses=E401, summary="Cria uma conversa vazia")
async def criar_conversa(request: Request, dono: UUID = Depends(usuario_atual)):
    return await repositorio.criar_conversa(request.app.state.pool, dono)


@router.get("/conversations/{conversation_id}", response_model=ConversaDetalhada, tags=["conversas"],
            responses={**E401, **E404}, summary="Conversa com todas as mensagens")
async def buscar_conversa(conversation_id: UUID, request: Request, dono: UUID = Depends(usuario_atual)):
    pool = request.app.state.pool
    conversa = await repositorio.buscar_conversa(pool, dono, conversation_id)
    if conversa is None:
        raise conversa_nao_encontrada()
    return {**conversa, "messages": await repositorio.listar_mensagens(pool, conversation_id)}


@router.post("/chat", response_model=RespostaChat, tags=["chat"],
             responses={**E401, **E404, **E429, **E503},
             summary="Envia uma pergunta e devolve a resposta do assistente")
async def chat(pedido: PedidoChat, request: Request, dono: UUID = Depends(usuario_atual)):
    state = request.app.state
    if not state.limites.chat_usuario.permitir(str(dono)) or not state.limites.chat_global.permitir("*"):
        raise muitas_requisicoes()

    perguntada_em = datetime.now(timezone.utc)
    historico: list[dict] = []
    if pedido.conversation_id is not None:
        if await repositorio.buscar_conversa(state.pool, dono, pedido.conversation_id) is None:
            raise conversa_nao_encontrada()
        historico = await repositorio.ultimas_mensagens(state.pool, pedido.conversation_id)

    pedido_orquestrador = PedidoResposta(
        question=pedido.message,
        profile=pedido.profile,
        temperature=pedido.temperature,
        history=[ItemHistorico(**item) for item in historico],
    )
    try:
        resposta = await state.orquestrador.responder(pedido_orquestrador, request.state.request_id)
    except OrquestradorIndisponivel:
        raise orquestrador_indisponivel()

    conversa_id, mensagem = await repositorio.gravar_troca(
        state.pool, dono, pedido.conversation_id, pedido.message, perguntada_em,
        resposta.model_dump(mode="json"),
    )
    log.info("request_id=%s conversa=%s mode=%s grounded=%s fontes=%d",
             request.state.request_id, conversa_id, resposta.mode, resposta.grounded, len(resposta.sources))
    return RespostaChat(conversation_id=conversa_id, message=mensagem)


@router.post("/feedback", response_model=Ok, tags=["feedback"], responses={**E401, **E404},
             summary="Registra ou remove o voto útil/não útil de uma resposta")
async def feedback(pedido: PedidoFeedback, request: Request, dono: UUID = Depends(usuario_atual)):
    if not await repositorio.votar(request.app.state.pool, dono, pedido.message_id, pedido.value):
        raise mensagem_nao_encontrada()
    return Ok()
