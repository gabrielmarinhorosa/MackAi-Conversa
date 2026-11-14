# mackai-conversas

Porta de entrada pública do **MackAI** (Módulo 7): entrega o front, identifica cada navegador com uma
sessão anônima, guarda conversas, mensagens e feedback no PostgreSQL e repassa as perguntas ao
`mackai-orquestrador`.

**Não faz:** montar prompt, chamar o Gemini, buscar trechos nem acessar o `busca_db`.

```text
Navegador ──HTTPS──► mackai-conversas ──► conversas_db (PostgreSQL)
                           │ POST /v1/answers (timeout de 60 s)
                           ▼
                     mackai-orquestrador ──► mackai-busca
```

Stack: Python 3.12, FastAPI, Pydantic v2, asyncpg (SQL puro, sem ORM), httpx, PyJWT; front em React + Vite.

## Rodar localmente

### Com Docker (PostgreSQL + Orquestrador falso + serviço)

```bash
docker compose up --build
```

Abra http://localhost:8000. A documentação interativa fica em http://localhost:8000/docs.

### Sem Docker

Pré-requisitos: Python 3.12+, Node 22 e um PostgreSQL com o banco `conversas_db`.

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # preencha SESSION_SECRET (32+ caracteres)
```

Em três terminais:

```bash
uvicorn dev.orquestrador_falso:app --port 8001      # ou o mackai-orquestrador real
uvicorn assistente_conversacional.main:app --port 8000 --reload
cd frontend && npm ci && npm run dev                # http://localhost:5173 (proxy de /api para 8000)
```

O orquestrador falso responde no mesmo contrato do real. Para testar a interface: uma pergunta com
"geral" volta sem fontes (`grounded=false`), "falha" gera 503 e "lento" estoura o timeout.

### Testes

Os testes usam um PostgreSQL de verdade (as tabelas são truncadas a cada teste) e um Orquestrador falso
(`httpx.MockTransport`).

```bash
TEST_DATABASE_URL=postgresql://mackai:mackai@localhost:5432/conversas_test pytest
```

## API pública

Contrato completo: [contracts/mackai-conversas.openapi.json](contracts/mackai-conversas.openapi.json)
(gerado por `python scripts/exportar_openapi.py`) e coleção do Postman em [postman/](postman/).

| Método | Rota | Token | Descrição |
|---|---|---|---|
| `POST` | `/api/sessions` | não | Cria uma sessão anônima e devolve `{token, expires_at}` |
| `GET` | `/api/health` | não | Estado agregado do Orquestrador e da Busca |
| `GET` | `/api/conversations` | sim | Conversas do dono do token que têm mensagens, da mais recente para a mais antiga |
| `POST` | `/api/conversations` | sim | Cria uma conversa vazia (201) |
| `GET` | `/api/conversations/{id}` | sim | Conversa com as mensagens |
| `POST` | `/api/chat` | sim | Envia a pergunta e devolve a resposta do assistente |
| `POST` | `/api/feedback` | sim | Vota `up`, `down` ou `null` (remove) numa resposta |
| `GET` | `/health` | não | Sonda de vida e prontidão (`{"status": "ok"}`) |

### Como outro módulo integra

1. `POST /api/sessions` → guarde o `token` (vale 30 dias).
2. Envie `Authorization: Bearer <token>` nas rotas `/api/*`. Em 401, crie outro token e repita uma vez.
3. Pergunte:

   ```bash
   curl -X POST http://localhost:8000/api/chat \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"message": "Como funciona a busca?", "conversation_id": null, "profile": "Desenvolvedor", "temperature": 0.4}'
   ```

4. Para continuar a conversa, envie o `conversation_id` devolvido. As 10 últimas mensagens vão como histórico.
5. Envie `X-Request-ID` se quiser correlacionar os logs; o serviço devolve o mesmo cabeçalho.

O token **não é login**: ele só isola um cliente do outro. Cada token enxerga apenas as próprias conversas.
Chamadas servidor a servidor não precisam de CORS. Se outro front, em outra origem, for chamar a API pelo
navegador, configure `CORS_ORIGINS`.

### Campos da resposta do chat

| Campo | Significado |
|---|---|
| `message.content` | Resposta em markdown |
| `message.sources[]` | `source` (módulo), `path`, `start_line`, `end_line`, `similarity` (0 a 1) e `excerpt` (300 caracteres) |
| `message.grounded` | `false` quando a resposta não veio de arquivos do projeto |
| `message.mode` | `gemini`, `offline` (sem chave) ou `fallback` (o Gemini falhou e a resposta é a mensagem amigável) |
| `message.feedback` | `up`, `down` ou `null` |

### Erros

Formato comum aos serviços: `{"detail": "mensagem legível", "code": "CODIGO"}`. Validação usa o 422 padrão do FastAPI.

| Status | `code` | Quando |
|---|---|---|
| 401 | `NAO_AUTENTICADO` | Sem token, token inválido ou expirado |
| 404 | `CONVERSA_NAO_ENCONTRADA` | Conversa não existe ou é de outro dono |
| 404 | `MENSAGEM_NAO_ENCONTRADA` | Mensagem não existe, é de outro dono ou não é do assistente |
| 422 | — | `message` vazia ou acima de 20.000 caracteres, perfil fora da lista, `temperature` fora de 0 a 1 |
| 429 | `RATE_LIMITED` | Mais de 10 perguntas por usuário, 60 no total ou 10 sessões por IP, por minuto |
| 503 | `ORQUESTRADOR_INDISPONIVEL` | Orquestrador fora do ar, lento (> 60 s) ou com resposta fora do contrato. Nada é gravado |

Perfis aceitos: `Desenvolvedor`, `Product Owner` e `Gerente de Projetos`.

## Dados

Tabelas `conversations` e `messages` em [schema.sql](assistente_conversacional/schema.sql), criadas na
inicialização com `CREATE TABLE IF NOT EXISTS`.

- Pergunta e resposta são gravadas na mesma transação, só depois que o Orquestrador responde.
- O título da conversa é formado pelos primeiros 60 caracteres da primeira pergunta.
- Dados de calibração (US 35):

  ```sql
  SELECT m.feedback, count(*) FROM messages m WHERE m.feedback IS NOT NULL GROUP BY m.feedback;
  ```

## Configuração

| Variável | Padrão | Observação |
|---|---|---|
| `DATABASE_URL` | `postgresql://mackai:mackai@localhost:5432/conversas_db` | Secret no Azure |
| `SESSION_SECRET` | — | Obrigatória, 32+ caracteres. Secret no Azure |
| `ORQUESTRADOR_URL` | `http://localhost:8001` | `http://mackai-orquestrador` no Azure |
| `ORQUESTRADOR_TIMEOUT_S` | `60` | |
| `CHAT_LIMIT_PER_USER` | `10` | Por minuto |
| `CHAT_LIMIT_GLOBAL` | `60` | Por minuto |
| `SESSION_LIMIT_PER_IP` | `10` | Por minuto, IP lido de `X-Forwarded-For` |
| `MAX_MESSAGE_CHARS` | `20000` | Mesmo valor de `MAX_MESSAGE_CHARS` em `frontend/src/assistente_conversacional/api.ts` |
| `CORS_ORIGINS` | vazio | Só para fronts em outra origem |

## Estrutura

```text
assistente_conversacional/
  main.py                   # app, handler de erros, X-Request-ID e montagem do front
  rotas.py                  # rotas /api/*
  modelos.py                # contrato público e contrato do Orquestrador (Pydantic)
  sessoes.py                # token JWT e dependência de autenticação
  limites.py                # limites por minuto em memória
  repositorio.py            # SQL de conversas e mensagens
  cliente_orquestrador.py   # httpx.AsyncClient reutilizado
  erros.py                  # erros no formato {detail, code}
  config.py                 # variáveis de ambiente
  schema.sql
frontend/                   # React + Vite, identidade visual do Módulo 6
dev/orquestrador_falso.py   # Orquestrador falso para desenvolvimento
contracts/                  # OpenAPI exportado e contrato consumido do Orquestrador
postman/                    # coleção e ambientes (gerados por scripts/gerar_postman.py)
tests/
```

## Deploy (Azure Container Apps)

- Container App `mackai-conversas`, ingress **externo**, porta 8000, 0,25 vCPU e 0,5 GiB.
- Réplicas: mínimo 0 e máximo 1 (os limites ficam em memória). No dia da apresentação, mínimo 1.
- Secrets: `DATABASE_URL` e `SESSION_SECRET`.
- Sondas de vida e de prontidão em `/health`.

## Limitações

- Quem perde o token perde o histórico. Login real (por exemplo, Microsoft Entra ID) é o próximo passo.
- Os contadores de limite zeram quando o serviço reinicia e não funcionam com mais de uma réplica.
- Sem streaming de resposta e sem exportação de feedback pela interface.
