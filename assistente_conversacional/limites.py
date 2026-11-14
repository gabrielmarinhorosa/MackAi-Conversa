"""Limites de requisição em memória, com janela deslizante de 1 minuto.

O app roda com no máximo 1 réplica, então contadores em memória bastam.
Eles zeram quando o serviço reinicia (risco aceito na seção 15).
"""

import time
from collections import deque


class Limite:
    def __init__(self, maximo: int, janela_s: float = 60):
        self.maximo = maximo
        self.janela_s = janela_s
        self._eventos: dict[str, deque[float]] = {}

    def permitir(self, chave: str) -> bool:
        agora = time.monotonic()
        fila = self._eventos.setdefault(chave, deque())
        while fila and agora - fila[0] >= self.janela_s:
            fila.popleft()
        if len(fila) >= self.maximo:
            return False
        fila.append(agora)
        self._limpar(agora)
        return True

    def _limpar(self, agora: float) -> None:
        # Evita que chaves de sessões antigas fiquem para sempre na memória (US 48).
        if len(self._eventos) < 1000:
            return
        for chave in [c for c, f in self._eventos.items() if not f or agora - f[-1] >= self.janela_s]:
            del self._eventos[chave]


class Limites:
    def __init__(self, por_usuario: int, global_: int, sessoes_por_ip: int):
        self.chat_usuario = Limite(por_usuario)
        self.chat_global = Limite(global_)
        self.sessoes_ip = Limite(sessoes_por_ip)


def ip_do_cliente(x_forwarded_for: str | None, ip_direto: str | None) -> str:
    """O ingress do Container Apps coloca o IP real no primeiro item de X-Forwarded-For."""
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return ip_direto or "desconhecido"
