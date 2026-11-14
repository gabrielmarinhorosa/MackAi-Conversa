"""Rotas públicas /api/*. Todas exigem o Bearer do Módulo 1, exceto `health`."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request

from . import repositorio
from .cliente_orquestrador import OrquestradorIndisponivel
from .erros import conversa_nao_encontrada, mensagem_nao_encontrada, muitas_requisicoes, orquestrador_indisponivel
from .modelos import (ConversaDetalhada, Erro, ItemHistorico, MetricasProjeto, Ok, PedidoChat, PedidoConversa,
                      PedidoFeedback, PedidoResposta, RespostaChat, ResumoConversa, Saude)
from .modulo1 import Sessao, exigir_acesso, sessao_atual

log = logging.getLogger("mackai.conversas")

router = APIRouter(prefix="/api")

E401 = {401: {"model": Erro, "description": "Token do Módulo 1 ausente, inválido ou de sessão encerrada"}}
E404 = {404: {"model": Erro, "description": "Não existe, é de outro dono ou o projeto não está acessível"}}
E429 = {429: {"model": Erro, "description": "Limite de requisições por minuto"}}
E503 = {503: {"model": Erro, "description": "Orquestrador ou Módulo 1 indisponível"}}


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


@router.get("/conversations", response_model=list[ResumoConversa], tags=["conversas"],
            responses={**E401, **E404, **E503},
            summary="Lista as conversas do usuário no projeto (ou as gerais) que têm mensagens")
async def listar_conversas(request: Request, sessao: Sessao = Depends(sessao_atual),
                           project_id: UUID | None = Query(None, description="Sem projeto = conversas gerais.")):
    await exigir_acesso(request, sessao, project_id)
    return await repositorio.listar_conversas(request.app.state.pool, sessao.usuario, project_id)


@router.post("/conversations", response_model=ResumoConversa, status_code=201, tags=["conversas"],
             responses={**E401, **E404, **E503}, summary="Cria uma conversa vazia")
async def criar_conversa(request: Request, sessao: Sessao = Depends(sessao_atual),
                         pedido: PedidoConversa | None = Body(None)):
    projeto = pedido.project_id if pedido else None
    await exigir_acesso(request, sessao, projeto)
    return await repositorio.criar_conversa(request.app.state.pool, sessao.usuario, projeto)


@router.get("/conversations/{conversation_id}", response_model=ConversaDetalhada, tags=["conversas"],
            responses={**E401, **E404, **E503}, summary="Conversa com todas as mensagens")
async def buscar_conversa(conversation_id: UUID, request: Request, sessao: Sessao = Depends(sessao_atual)):
    pool = request.app.state.pool
    conversa = await repositorio.buscar_conversa(pool, sessao.usuario, conversation_id)
    if conversa is None:
        raise conversa_nao_encontrada()
    await exigir_acesso(request, sessao, conversa["project_id"])
    return {**conversa, "messages": await repositorio.listar_mensagens(pool, conversation_id)}


@router.post("/chat", response_model=RespostaChat, tags=["chat"],
             responses={**E401, **E404, **E429, **E503},
             summary="Envia uma pergunta e devolve a resposta do assistente")
async def chat(pedido: PedidoChat, request: Request, sessao: Sessao = Depends(sessao_atual)):
    state = request.app.state
    dono = sessao.usuario
    if not state.limites.chat_usuario.permitir(str(dono)) or not state.limites.chat_global.permitir("*"):
        raise muitas_requisicoes()

    perguntada_em = datetime.now(timezone.utc)
    projeto = pedido.project_id
    historico: list[dict] = []
    if pedido.conversation_id is not None:
        conversa = await repositorio.buscar_conversa(state.pool, dono, pedido.conversation_id)
        if conversa is None:
            raise conversa_nao_encontrada()
        projeto = conversa["project_id"]
        historico = await repositorio.ultimas_mensagens(state.pool, pedido.conversation_id)
    await exigir_acesso(request, sessao, projeto)

    pedido_orquestrador = PedidoResposta(
        question=pedido.message,
        profile=pedido.profile,
        temperature=pedido.temperature,
        history=[ItemHistorico(**item) for item in historico],
        project_id=projeto,
    )
    try:
        resposta = await state.orquestrador.responder(pedido_orquestrador, request.state.request_id)
    except OrquestradorIndisponivel:
        raise orquestrador_indisponivel()

    conversa_id, mensagem = await repositorio.gravar_troca(
        state.pool, dono, pedido.conversation_id, projeto, pedido.message, perguntada_em,
        resposta.model_dump(mode="json"),
    )
    log.info("request_id=%s conversa=%s projeto=%s mode=%s grounded=%s fontes=%d", request.state.request_id,
             conversa_id, projeto, resposta.mode, resposta.grounded, len(resposta.sources))
    return RespostaChat(conversation_id=conversa_id, message=mensagem)


@router.post("/feedback", response_model=Ok, tags=["feedback"], responses={**E401, **E404, **E503},
             summary="Registra ou remove o voto útil/não útil de uma resposta")
async def feedback(pedido: PedidoFeedback, request: Request, sessao: Sessao = Depends(sessao_atual)):
    if not await repositorio.votar(request.app.state.pool, sessao.usuario, pedido.message_id, pedido.value):
        raise mensagem_nao_encontrada()
    return Ok()


@router.get("/projects/{project_id}/metrics", response_model=MetricasProjeto, tags=["integração"],
            responses={**E401, **E404, **E503},
            summary="Uso do assistente no projeto, somando todas as pessoas (para dashboards e relatórios)")
async def metricas(project_id: UUID, request: Request, sessao: Sessao = Depends(sessao_atual)):
    await exigir_acesso(request, sessao, project_id)
    return await repositorio.metricas_projeto(request.app.state.pool, project_id)
