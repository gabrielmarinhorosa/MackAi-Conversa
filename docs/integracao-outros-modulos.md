# Integração com o Módulo 7 (MackAI)

Este guia mostra como os outros módulos se integram ao assistente RAG do Módulo 7. A integração
acontece pela API pública do `mackai-conversas`. O Orquestrador e a Busca têm ingress interno e não
recebem chamadas de fora do Módulo 7.

| Componente | Endereço |
| --- | --- |
| Front e API (`mackai-conversas`) | `https://<url-publica-do-mackai-conversas>` |
| Documentação interativa | `https://<url-publica-do-mackai-conversas>/docs` |
| Contrato OpenAPI | [contracts/mackai-conversas.openapi.json](../contracts/mackai-conversas.openapi.json) |
| Coleção do Postman | [postman/](../postman/) |

## Quem integra com quem

| Módulo | Direção | O que é trocado |
| --- | --- | --- |
| **1. Autenticação, projetos e backlog** | O Módulo 7 consome | Login, validação do JWT, sessão ativa (`/auth/me`) e acesso ao projeto (`/projects/{id}/access/v2`) |
| **2. GitHub** | O Módulo 7 consome, pela Busca | Código e commits do repositório do projeto para indexar |
| **3. Artefatos** | O Módulo 7 consome, pela Busca | Documentos, User Stories, atas e diagramas para indexar |
| **5. Curadoria** | Os dois lados | O Módulo 7 pode indexar as recomendações. O Módulo 5 pode perguntar ao assistente sobre a stack do projeto |
| **4. Code Review** | O Módulo 4 consome | Perguntas ao assistente sobre a arquitetura do projeto |
| **6. Dashboard e portal** | O Módulo 6 consome | Link para o assistente no portal e métricas de uso para o dashboard |
| **8. Relatórios** | O Módulo 8 consome | Métricas de uso e perguntas ao assistente para gerar relatórios |

## Autenticação: a mesma conta do Módulo 1

Não existe login próprio do Módulo 7. Use o `access_token` do Módulo 1, o mesmo que o seu módulo já
usa nas APIs de Projetos e Backlog:

```http
Authorization: Bearer <access_token do Módulo 1>
```

Em cada chamada, o `mackai-conversas` faz três verificações:

1. Valida o JWT: RS256, `kid` do JWKS do Módulo 1, issuer e audiência `engenharia-software-api`.
   Esses valores vêm da configuração do serviço, nunca do token.
2. Consulta `GET /auth/me` com o mesmo Bearer para confirmar que a sessão e a conta estão ativas.
3. Quando a chamada envolve um projeto, consulta `GET /projects/{project_id}/access/v2` e exige a
   permissão `project:read`.

Os resultados de 2 e 3 ficam em cache por 60 segundos (`MOD1_CACHE_S`). Uma sessão encerrada no
Módulo 1 deixa de funcionar aqui em até 60 segundos. Uma negação de acesso não fica em cache: quem
aceita um convite entra na hora.

Não envie token em URL e não use token fixo compartilhado entre módulos. Chamadas de servidor
devem usar o token da pessoa que pediu a ação.

## Projetos

- `project_id` é o UUID do projeto na API de Projetos do Módulo 1. Ele não é o ID do usuário nem o
  ID do repositório no GitHub.
- Cada conversa pertence a uma pessoa (`sub` do JWT) e, opcionalmente, a um projeto. Sem
  `project_id`, a conversa é geral.
- Projeto inexistente ou sem acesso responde `404 PROJETO_NAO_ENCONTRADO`, como o Módulo 1
  recomenda.

## Rotas para outros módulos

| Método | Rota | Uso típico |
| --- | --- | --- |
| `POST` | `/api/chat` | Fazer uma pergunta ao assistente (Módulos 4, 5 e 8) |
| `GET` | `/api/conversations?project_id=` | Listar as conversas da pessoa no projeto |
| `GET` | `/api/conversations/{id}` | Ler uma conversa com as fontes de cada resposta |
| `POST` | `/api/feedback` | Votar `up` ou `down` numa resposta |
| `GET` | `/api/projects/{project_id}/metrics` | Números de uso do projeto (Módulos 6 e 8) |
| `GET` | `/api/health` | Estado do assistente (sem token) |

### Perguntar ao assistente

```bash
curl -X POST https://<url-publica-do-mackai-conversas>/api/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message": "Quais serviços dependem do banco de pedidos?", "project_id": "<uuid do projeto>",
       "conversation_id": null, "profile": "Desenvolvedor", "temperature": 0.4}'
```

A resposta traz `conversation_id` e `message`. A mensagem tem `content` (markdown), `sources`
(arquivo, linhas, similaridade e trecho), `grounded` (`false` quando a resposta não veio dos arquivos
do projeto) e `mode`. Para continuar a conversa, envie o `conversation_id` devolvido. O projeto da
conversa vale nas perguntas seguintes.

`profile` aceita `Desenvolvedor`, `Product Owner` e `Gerente de Projetos` e muda o foco da resposta.
O perfil não é permissão: o acesso vem do Módulo 1.

O tempo de resposta pode chegar a 60 segundos. Use um timeout de pelo menos 65 segundos e não repita
automaticamente uma pergunta que deu timeout.

### Métricas do projeto (dashboard e relatórios)

```bash
curl https://<url-publica-do-mackai-conversas>/api/projects/<uuid do projeto>/metrics \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "project_id": "7a1d0f4e-2b6c-4c1e-9f3a-5d8e7c6b4a01",
  "conversations": 12,
  "users": 4,
  "questions": 57,
  "answers_up": 21,
  "answers_down": 3,
  "answers_not_grounded": 6,
  "last_question_at": "2026-11-14T22:24:53Z"
}
```

Os números somam todas as pessoas do projeto. A rota não devolve o texto das conversas, que é
visível só para quem perguntou.

### Exemplo em Python

```python
import httpx

with httpx.Client(timeout=65) as cliente:
    resposta = cliente.post(
        "https://<url-publica-do-mackai-conversas>/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Resuma a arquitetura do projeto", "project_id": project_id},
    )
    resposta.raise_for_status()
    print(resposta.json()["message"]["content"])
```

## Abrir o assistente pelo portal (Módulo 6)

Use um link para o front do `mackai-conversas`. A pessoa entra com a mesma conta do Módulo 1. O token
não pode ir na URL, então o login acontece de novo no domínio do Módulo 7.

## Chamadas pelo navegador (CORS)

Chamadas de servidor não precisam de CORS. Se o front do seu módulo chamar esta API pelo navegador,
envie ao Módulo 7 a origem exata (esquema, host e porta, sem caminho). Ela entra em `CORS_ORIGINS`.

## Erros

Formato comum: `{"detail": "mensagem legível", "code": "CODIGO"}`.

| Status | `code` | O que fazer |
| --- | --- | --- |
| 401 | `NAO_AUTENTICADO` | Token ausente, inválido, expirado ou de sessão encerrada. Renove no Módulo 1 (`POST /auth/refresh`) ou faça login |
| 404 | `PROJETO_NAO_ENCONTRADO` | O projeto não existe ou a conta não tem `project:read`. Peça um convite ao dono do projeto |
| 404 | `CONVERSA_NAO_ENCONTRADA` | A conversa não existe ou é de outra pessoa |
| 404 | `MENSAGEM_NAO_ENCONTRADA` | A mensagem não existe, é de outra pessoa ou não é do assistente |
| 422 | — | Corpo inválido: `message` vazia ou acima de 20.000 caracteres, perfil fora da lista, `temperature` fora de 0 a 1 |
| 429 | `RATE_LIMITED` | Mais de 10 perguntas por pessoa ou 60 no total por minuto. Aguarde um minuto |
| 503 | `ORQUESTRADOR_INDISPONIVEL` | O assistente não respondeu. Nada foi gravado |
| 503 | `MODULO1_INDISPONIVEL` | O Módulo 1 não respondeu. Tente de novo em instantes |

Envie `X-Request-ID` para correlacionar os logs. O serviço devolve o mesmo cabeçalho.

## O que o Módulo 7 precisa dos outros módulos

| Módulo | Pedido | Situação |
| --- | --- | --- |
| 1 | Liberar no CORS de Identidade e Projetos a origem do front do Módulo 7 no Azure e `http://localhost:5173` | A enviar |
| 2 | Contrato para ler os arquivos do repositório de cada `project_id` | A combinar com a Busca |
| 3 | Contrato para ler os artefatos de cada `project_id` | A combinar com a Busca |
| 5 | Contrato das recomendações de curadoria | A combinar |
| 6 e 8 | Confirmar se as métricas acima bastam | A combinar |

## Limitações atuais

- A Busca ainda indexa um único conjunto de arquivos. O `project_id` já chega ao Orquestrador, mas a
  resposta só fica restrita ao projeto quando a Busca indexar por projeto.
- Os limites por minuto ficam em memória, com no máximo 1 réplica.
