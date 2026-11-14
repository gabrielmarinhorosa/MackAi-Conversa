# Contrato consumido do mackai-orquestrador

O Conversas só chama estas duas rotas. Se o Orquestrador mudar o contrato, o modelo `RespostaOrquestrador`
em `assistente_conversacional/modelos.py` e o orquestrador falso em `dev/orquestrador_falso.py` precisam mudar junto.

## `POST /v1/answers` (timeout de 60 s)

Cabeçalho: `X-Request-ID` (o mesmo que o Conversas recebeu ou gerou).

```json
{
  "question": "E para o PO?",
  "profile": "Product Owner",
  "temperature": 0.4,
  "history": [
    { "role": "user", "content": "Quais User Stories podemos simplificar?" },
    { "role": "assistant", "content": "..." }
  ],
  "project_id": "7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01"
}
```

- `history`: as 10 últimas mensagens da conversa, em ordem cronológica, cada uma cortada em 4.000 caracteres. Vazio numa conversa nova.
- `project_id` (novo, opcional): UUID do projeto do Módulo 1 da conversa. O campo **só é enviado** quando a
  conversa tem projeto, e o acesso da pessoa ao projeto já foi conferido pelo Conversas. O Orquestrador
  precisa aceitar o campo (não recusar campos extras) e repassá-lo à Busca para filtrar os trechos do projeto.

Resposta 200 usada pelo Conversas: `content`, `mode`, `grounded` e `sources` (cada fonte com `source`, `path`,
`start_line`, `end_line`, `similarity` e `excerpt`). `model` e `usage` são aceitos e ignorados.

Qualquer outra coisa (erro de rede, timeout, status diferente de 200 ou corpo fora do contrato) vira
`503 ORQUESTRADOR_INDISPONIVEL` no Conversas, sem gravar nada.

## `GET /v1/status` (timeout de 5 s)

```json
{ "llm": "gemini", "model": "gemini-2.5-flash", "busca": { "strategy": "embedding", "documents": 42, "chunks": 380, "indexed_at": "2026-11-12T10:00:00Z" } }
```

Usado para montar `GET /api/health`:

| Situação | `/api/health` |
|---|---|
| Orquestrador e Busca respondem | `status: "ok"`, `llm`, `documents`, `chunks` e `indexed_at` repassados |
| Orquestrador responde, `busca` nulo | `status: "degraded"`, `llm` repassado, contagens em 0 |
| Orquestrador não responde | `status: "degraded"`, `llm: "offline"`, contagens em 0, `indexed_at: null` |
