# Deploy do MackAI no Azure pelo portal

Guia passo a passo para publicar o `mackai-conversas` em [portal.azure.com](https://portal.azure.com) e
dar acesso aos colegas do grupo. Os nomes dos menus estão em português, com o nome em inglês entre
parênteses. O portal muda de vez em quando, então um rótulo pode estar um pouco diferente.

## Visão geral

Os três serviços do Módulo 7 precisam ficar no **mesmo ambiente do Container Apps** (`mackai-env`). O
Orquestrador e a Busca têm ingress interno: só um app do mesmo ambiente consegue chamá-los, por
`http://mackai-orquestrador` e `http://mackai-busca`. Um ambiente pertence a uma única assinatura.

Por isso **uma pessoa hospeda tudo na própria assinatura** e convida as outras. As outras pessoas
recebem acesso só ao grupo de recursos `mackai-rg`, não ao resto da assinatura.

| Recurso | Nome | Quem cria |
| --- | --- | --- |
| Grupo de recursos | `mackai-rg` | Dono da assinatura |
| Banco PostgreSQL | `mackai-pg`, com `conversas_db` e `busca_db` | Dono da assinatura |
| Imagem do contêiner | `ghcr.io/gabrielmarinhorosa/mackai-conversas` | GitHub Actions |
| Ambiente do Container Apps | `mackai-env` | Criado junto com o primeiro app |
| Container App | `mackai-conversas` (ingress externo) | Gabriel |
| Container App | `mackai-orquestrador` (ingress interno) | Lucas |
| Container App | `mackai-busca` (ingress interno) | Danilo |

Use **a mesma região em todos os recursos**. O exemplo usa Brazil South. Se a assinatura de estudante
recusar a região, escolha outra permitida e use essa em tudo.

**Custos:** o PostgreSQL B1ms e o Container Apps têm cota gratuita para estudantes. Confira o aviso de
gratuidade na tela de criação. As imagens ficam no GitHub Container Registry, sem custo. Acompanhe em **Gerenciamento de Custos (Cost Management)**.

---

## Parte 1 — Dono da assinatura: grupo de recursos e acesso dos colegas

### 1.1 Criar o grupo de recursos

1. No portal, busque **Grupos de recursos (Resource groups)** na barra de pesquisa do topo.
2. Clique em **+ Criar (Create)**.
3. Preencha:
   - **Assinatura:** Azure for Students.
   - **Grupo de recursos:** `mackai-rg`.
   - **Região:** Brazil South.
4. Clique em **Revisar + criar (Review + create)** e depois em **Criar (Create)**.

### 1.2 Convidar os colegas para o diretório (geralmente não é preciso)

Na assinatura Azure for Students, o diretório costuma ser o da universidade, e o Microsoft Entra ID é
administrado pela TI da faculdade. Nesse caso você não tem acesso a ele, mas também não precisa
convidar ninguém: os colegas que entram com o e-mail da faculdade já estão no mesmo diretório. Pule
para a etapa 1.3 e busque o colega pelo e-mail da faculdade.

Só faça os passos abaixo se tiver acesso ao Entra ID e o colega usar um e-mail de fora do diretório.

1. Busque **Microsoft Entra ID** na barra de pesquisa.
2. No menu lateral, abra **Usuários (Users)**.
3. Clique em **+ Novo usuário (New user)** e depois em **Convidar usuário externo (Invite external user)**.
4. Preencha o **E-mail** do colega. O nome de exibição é opcional.
5. Clique em **Revisar + convidar (Review + invite)** e depois em **Convidar (Invite)**.
6. Repita para cada colega.

O colega recebe um e-mail da Microsoft com o convite.

### 1.3 Dar acesso ao `mackai-rg`

1. Abra o grupo de recursos `mackai-rg`.
2. No menu lateral, abra **Controle de acesso (IAM) (Access control (IAM))**.
3. Clique em **+ Adicionar (Add)** e depois em **Adicionar atribuição de função (Add role assignment)**.
4. Na aba **Função (Role)**, abra a subaba **Funções de administrador privilegiado (Privileged administrator roles)**.
   Selecione **Colaborador (Contributor)** e clique em **Avançar (Next)**.
5. Na aba **Membros (Members)**, deixe **Usuário, grupo ou entidade de serviço** marcado e clique em
   **+ Selecionar membros (Select members)**.
6. Busque pelo e-mail do colega, de preferência o da faculdade. Selecione e clique em **Selecionar (Select)**.
7. Clique em **Revisar + atribuir (Review + assign)** duas vezes.

Com o papel Colaborador no `mackai-rg`, o colega cria e altera recursos só dentro desse grupo.

Se a busca não encontrar o colega, ele não está no seu diretório. Tente o e-mail da faculdade. Se
ainda assim não aparecer, veja "Plano B" no fim da Parte 1.

### 1.4 O que cada colega faz para entrar

1. Entra em [portal.azure.com](https://portal.azure.com) com a conta da faculdade, a mesma que você buscou na etapa 1.3.
2. Clica na **engrenagem (Configurações)** no topo e abre **Diretórios + assinaturas (Directories + subscriptions)**.
3. Confere se o diretório atual é o da faculdade. Se não for, clica em **Alternar (Switch)** nele.
4. Na mesma tela, em **Filtro de assinatura padrão (Default subscription filter)**, marca a sua
   assinatura **Azure for Students**. Ela aparece com o mesmo nome da dele, então confira pelo ID da
   assinatura, que você manda para ele.
5. Busca **Grupos de recursos** e confere se o `mackai-rg` aparece.

Se o colega foi convidado como externo (etapa 1.2), antes ele abre o e-mail e clica em **Aceitar
convite**, e no passo 3 alterna para o diretório do dono da assinatura.

Se o `mackai-rg` não aparecer, o colega está no diretório errado, o filtro de assinatura esconde a
sua, ou a atribuição da etapa 1.3 não foi feita.

### Plano B: quando não dá para dar acesso

Se o colega não puder entrar no `mackai-rg`, o dono da assinatura cria os três apps sozinho, seguindo as
Partes 4 e 5 com o repositório de cada colega. Cada colega precisa autorizar o Azure no GitHub para o
repositório dele, ou dar ao dono acesso de administrador ao repositório. A chave do Gemini do Lucas é
digitada pelo próprio Lucas, numa chamada de vídeo com tela compartilhada, ou o grupo usa uma chave do dono.

---

## Parte 2 — Dono da assinatura: banco de dados

### 2.1 Criar o servidor PostgreSQL

1. Busque **Servidores flexíveis do Banco de Dados do Azure para PostgreSQL**
   (**Azure Database for PostgreSQL flexible servers**) e clique em **+ Criar (Create)**.
2. Aba **Básico (Basics)**:
   - **Grupo de recursos:** `mackai-rg`.
   - **Nome do servidor:** `mackai-pg`. Se o nome já existir no Azure, use um sufixo, como `mackai-pg-m7`.
   - **Região:** Brazil South.
   - **Versão do PostgreSQL:** 16.
   - **Tipo de carga de trabalho:** Desenvolvimento (Development).
   - **Computação + armazenamento:** clique em **Configurar servidor** e escolha **Com intermitência
     (Burstable)**, **Standard_B1ms**, armazenamento de 32 GiB. Em **Alta disponibilidade**, deixe desativada.
     Clique em **Salvar**.
   - **Método de autenticação:** Somente autenticação do PostgreSQL.
   - **Nome de usuário do administrador:** `mackai`.
   - **Senha:** crie uma senha forte e guarde num gerenciador de senhas. Ela não vai para o chat nem
     para o repositório.
3. Aba **Rede (Networking)**:
   - **Método de conectividade:** Acesso público (endereços IP permitidos).
   - Marque **Permitir acesso público de qualquer serviço do Azure dentro do Azure a este servidor**.
   - Não adicione o IP `0.0.0.0–255.255.255.255`.
4. Clique em **Revisar + criar** e depois em **Criar**. A criação leva alguns minutos.

### 2.2 Criar os bancos

1. Abra o servidor `mackai-pg`.
2. No menu lateral, em **Configurações**, abra **Bancos de dados (Databases)**.
3. Clique em **+ Adicionar**, digite `conversas_db` e clique em **Salvar**.
4. Repita para `busca_db`.

### 2.3 Liberar o pgvector (para a Busca)

1. No servidor, abra **Parâmetros do servidor (Server parameters)**.
2. Busque `azure.extensions`.
3. Marque **VECTOR** na lista de valores e clique em **Salvar**.

### 2.4 Montar as cadeias de conexão

Troque `<SENHA>` pela senha do administrador. Se o nome do servidor tiver sufixo, troque também `mackai-pg`.

```text
Conversas: postgresql://mackai:<SENHA>@mackai-pg.postgres.database.azure.com:5432/conversas_db?sslmode=require
Busca:     postgresql://mackai:<SENHA>@mackai-pg.postgres.database.azure.com:5432/busca_db?sslmode=require
```

Envie a cadeia da Busca ao Danilo por um canal privado, nunca num grupo aberto ou no repositório. Se
a senha tiver caracteres como `@`, `:` ou `/`, eles precisam ser codificados (`@` vira `%40`).

---

## Parte 3 — Imagem do contêiner (GitHub Container Registry)

O Container Apps roda imagens de contêiner. Na assinatura de estudante, o Azure Container Registry não
monta imagens (`az acr build` responde `TasksOperationsNotAllowed`), e a implantação contínua do portal
trava com o registro vazio. Por isso a imagem é montada pelo **GitHub Actions** e publicada no
**GitHub Container Registry** (`ghcr.io`), sem custo e sem credencial do Azure.

1. A cada push na `main`, o workflow `ci` (`.github/workflows/ci.yml`) roda os testes, monta a imagem
   e publica `ghcr.io/gabrielmarinhorosa/mackai-conversas:latest` e uma tag com o commit (7 caracteres).
2. Na primeira vez, deixe o pacote público para o Azure conseguir baixar sem senha:
   - No GitHub, abra o seu perfil e a aba **Packages**, ou o link **Packages** na lateral do repositório.
   - Abra `mackai-conversas` e clique em **Package settings**.
   - Em **Danger Zone**, clique em **Change visibility**, escolha **Public** e confirme.
   - O código do repositório já é público, então a imagem não expõe nada novo. Os segredos (banco,
     chaves) ficam no Azure, não na imagem.

Se um registro de contêineres (ACR) já foi criado, ele não é usado. Ele custa cerca de US$ 5 por mês
e pode ser excluído.

---

## Parte 4 — Gabriel: Container App `mackai-conversas`

### 4.1 Criar o app e o ambiente

1. Busque **Aplicativos de Contêiner (Container Apps)** e clique em **+ Criar (Create)**. Se houver
   opções, escolha **Aplicativo de Contêiner (Container App)**.
2. Aba **Básico (Basics)**:
   - **Grupo de recursos:** `mackai-rg`.
   - **Nome do aplicativo de contêiner:** `mackai-conversas`.
   - **Origem da implantação (Deployment source):** Imagem de contêiner (Container image).
   - **Região:** Brazil South.
   - **Ambiente de Aplicativos de Contêiner:** clique em **Criar novo (Create new)**:
     - **Nome do ambiente:** `mackai-env`.
     - **Perfis de carga de trabalho (Workload profiles):** mantenha só o perfil **Consumption**, que já vem
       na lista. Não adicione perfis *Dedicated*: eles cobram por hora mesmo sem uso. Em portais mais
       antigos, a opção equivalente se chama **Somente consumo (Consumption only)**.
     - Na aba **Monitoramento**, em **Destino dos logs (Logs Destination)**, escolha **Don't save logs**.
       Não tem custo, e o **Fluxo de log** continua mostrando os logs ao vivo. Se precisar de histórico,
       troque depois para Azure Monitor (cobrado por GB armazenado).
     - Clique em **Criar**.
3. Aba **Contêiner (Container)**:
   - Marque **Usar imagem de início rápido (Use quickstart image)**. A imagem real entra na etapa 4.4.
4. Aba **Entrada (Ingress)**:
   - **Entrada:** Habilitada.
   - **Tráfego de entrada:** Aceitando tráfego de qualquer lugar (Accepting traffic from anywhere).
   - **Tipo de entrada:** HTTP.
   - **Porta de destino:** 80 por enquanto, porque a imagem de início rápido usa a porta 80. Ela muda para 8000 na etapa 4.5.
5. Clique em **Revisar + criar** e depois em **Criar**.

### 4.2 Guardar o secret do banco

1. Abra o app `mackai-conversas`.
2. Em **Configurações**, abra **Segredos (Secrets)** e clique em **+ Adicionar**.
3. Preencha:
   - **Chave:** `database-url`.
   - **Tipo:** Segredo do Aplicativo de Contêiner (Container Apps Secret).
   - **Valor:** a cadeia de conexão do Conversas, da etapa 2.4.
4. Clique em **Adicionar**.

### 4.3 Escala e recursos

1. Em **Aplicativo**, abra **Escala (Scale)**, ou **Escala e réplicas**.
2. Coloque **Mínimo de réplicas** 0 e **Máximo de réplicas** 1 e salve.
   O máximo precisa ser 1: os limites de perguntas por minuto ficam na memória do app.
   No dia da apresentação, coloque o mínimo em 1 para o app não demorar a acordar. Depois volte para 0.

### 4.4 Apontar o app para a imagem

Faça esta etapa depois que o workflow da Parte 3 publicar a imagem e o pacote estiver público.

1. Em **Aplicativo**, abra **Contêineres (Containers)** e clique em **Editar e implantar (Edit and deploy)**.
2. Selecione o contêiner e clique em **Editar**.
3. Preencha:
   - **Origem da imagem (Image source):** Docker Hub ou outros registros (Docker Hub or other registries).
   - **Tipo de imagem:** Público (Public).
   - **Servidor de logon do registro (Registry login server):** `ghcr.io`.
   - **Imagem e marca (Image and tag):** `gabrielmarinhorosa/mackai-conversas:latest`.
4. Siga para a etapa 4.5 na mesma tela, antes de salvar.

**Para publicar uma versão nova:** depois de um push na `main` com o workflow concluído, abra
**Contêineres → Editar e implantar** e clique em **Criar**. Isso gera uma revisão nova, que baixa a
imagem `latest` atual. Para fixar uma versão, use a tag do commit no lugar de `latest`.

### 4.5 Variáveis de ambiente e porta

Na mesma tela de edição do contêiner da etapa 4.4:

1. Confira se a **Imagem** é `ghcr.io/gabrielmarinhorosa/mackai-conversas:latest`, e não a de início rápido.
2. **Recursos:** CPU 0,25 e memória 0,5 Gi.
3. Em **Variáveis de ambiente (Environment variables)**, adicione:

   | Nome | Origem | Valor |
   | --- | --- | --- |
   | `DATABASE_URL` | Referenciar um segredo (Reference a secret) | `database-url` |
   | `ORQUESTRADOR_URL` | Manual | `http://mackai-orquestrador` |

   As variáveis `MOD1_*` não precisam ser criadas: os valores padrão já apontam para o Módulo 1 publicado.
4. Na aba **Investigações de integridade (Health probes)**, se existir, configure a investigação de
   **Atividade (Liveness)** e de **Preparação (Readiness)** como HTTP, caminho `/health`, porta 8000.
5. Clique em **Salvar** e depois em **Criar** para gerar a revisão nova.
6. Em **Configurações**, abra **Entrada (Ingress)**, mude a **Porta de destino** para `8000` e salve.

### 4.6 Testar

1. Na **Visão geral (Overview)** do app, copie a **URL do Aplicativo (Application Url)**.
2. Abra `<URL>/health`. A resposta deve ser `{"status":"ok"}`.
3. Abra `<URL>/api/health`. Enquanto o Orquestrador não estiver no ar, a resposta é
   `{"status":"degraded","llm":"offline",...}`, e isso é esperado.
4. Abra `<URL>/`. A tela de login aparece. O login só funciona depois que o Módulo 1 liberar a URL no CORS.

Se o app não subir, abra **Monitoramento → Fluxo de log (Log stream)**. Os erros mais comuns são o
`DATABASE_URL` errado e o banco recusando a conexão (confira a etapa 2.1, aba Rede).

### 4.7 Depois do deploy

1. Envie a URL ao Módulo 1 para liberarem o CORS de Identidade e Projetos.
2. Troque `<url-publica-do-mackai-conversas>` em `docs/integracao-outros-modulos.md` e no ambiente
   `mackai-azure` do Postman (`scripts/gerar_postman.py`).

---

## Parte 5 — Lucas e Danilo: Orquestrador e Busca

Cada um faz as Partes 3 e 4 com o próprio repositório (workflow que publica no `ghcr.io`), depois de entrar no diretório (etapa 1.4), com estas diferenças:

| | Lucas | Danilo |
| --- | --- | --- |
| Nome do app (exato) | `mackai-orquestrador` | `mackai-busca` |
| Ambiente | Selecionar o `mackai-env` existente (não criar outro) | Igual |
| Entrada | **Limitada ao Ambiente de Aplicativos de Contêiner** (interno), porta 8000 | Igual |
| Secrets | `GEMINI_API_KEY`, cadastrada só pelo Lucas | `GEMINI_API_KEY` e `DATABASE_URL` do `busca_db` |
| Variável | `BUSCA_URL=http://mackai-busca` | — |
| Escala | Mínimo 0, máximo 1, CPU 0,25, memória 0,5 Gi | Igual |

- O nome do app precisa ser exato: ele vira o endereço interno que os outros serviços chamam.
- Se as chamadas internas falharem por redirecionamento para HTTPS, ative **Permitir conexões inseguras
  (Allow insecure connections)** em **Entrada**.
- **Lucas:** o Conversas envia `project_id` (opcional) em `POST /v1/answers`. O Orquestrador precisa
  aceitar o campo. Detalhes em [contracts/orquestrador-consumido.md](../contracts/orquestrador-consumido.md).
- **Danilo:** para as respostas ficarem restritas a um projeto, a Busca precisa indexar e filtrar por `project_id`.

## Ordem recomendada

1. Dono da assinatura: Partes 1 e 2. Push na `main` para a Parte 3.
2. Gabriel: Parte 4 (cria o `mackai-env`).
3. Danilo: Busca (Parte 5).
4. Lucas: Orquestrador (Parte 5).
5. Teste de ponta a ponta: `/api/health` do Conversas com `status: "ok"` e uma pergunta respondida com fontes.
