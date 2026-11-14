"""Cliente HTTP do mackai-orquestrador. Um único httpx.AsyncClient por app (US 5 e 48)."""

import logging

import httpx
from pydantic import ValidationError

from .modelos import PedidoResposta, RespostaOrquestrador

log = logging.getLogger("mackai.conversas")


class OrquestradorIndisponivel(Exception):
    pass


class ClienteOrquestrador:
    def __init__(self, base_url: str, timeout_s: float, status_timeout_s: float,
                 transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)
        self._status_timeout_s = status_timeout_s

    async def responder(self, pedido: PedidoResposta, request_id: str) -> RespostaOrquestrador:
        """POST /v1/answers. Qualquer falha (rede, timeout, status != 200, corpo inválido) vira 503."""
        try:
            resposta = await self._http.post(
                "/v1/answers", json=pedido.model_dump(mode="json"), headers={"X-Request-ID": request_id}
            )
            resposta.raise_for_status()
            return RespostaOrquestrador.model_validate(resposta.json())
        except (httpx.HTTPError, ValidationError, ValueError) as erro:
            log.warning("request_id=%s orquestrador falhou: %r", request_id, erro)
            raise OrquestradorIndisponivel() from erro

    async def status(self, request_id: str) -> dict | None:
        """GET /v1/status. Devolve None se o Orquestrador não responder."""
        try:
            resposta = await self._http.get(
                "/v1/status", headers={"X-Request-ID": request_id}, timeout=self._status_timeout_s
            )
            resposta.raise_for_status()
            return resposta.json()
        except (httpx.HTTPError, ValueError) as erro:
            log.warning("request_id=%s status do orquestrador falhou: %r", request_id, erro)
            return None

    async def fechar(self) -> None:
        await self._http.aclose()
