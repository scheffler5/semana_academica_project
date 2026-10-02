# 📦 Estoque Inteligente: laboratório AWS (Cloud Practitioner)

Sistema simples de controle de estoque com **assistente de IA**, feito para demonstrar
em aula um deploy real na AWS usando 7 serviços:

| Serviço | Papel no projeto |
|---|---|
| **Amazon VPC + Internet Gateway** | Rede isolada. Sub-rede pública (EC2) com saída para a internet; sub-redes privadas (Aurora e Lambda) sem acesso direto. |
| **Amazon EC2** | Servidor que hospeda o site (React + nginx) e a API (Python/FastAPI). |
| **Amazon Aurora (PostgreSQL Serverless v2)** | Banco de dados dos itens e movimentações. |
| **Amazon S3** | Fotos dos itens em bucket privado (servidas pela API, sem expor credenciais). |
| **Amazon Bedrock (Agents)** | Agente de IA generativa: entende português e decide quais ações executar. |
| **AWS Lambda** | As "ferramentas" do agente: consultam/alteram o estoque chamando a API pela rede privada. |
| **Amazon CloudWatch / IAM** | Logs da API e da Lambda; roles com privilégio mínimo (nenhuma chave de acesso no código). |

A previsão de demanda (em quantos dias um item acaba) é calculada no próprio backend por média móvel.

## Arquitetura

O diagrama da arquitetura é desenhado pelo próprio sistema (código em
`frontend/src/components/ArchitectureDiagram.jsx`): abra a tela **Arquitetura AWS** para ver o status
de cada serviço ao vivo e use **Baixar PNG** para levar a imagem para os slides.

> O repositório guarda **só código**: nenhuma imagem nem banco de dados é versionado. As tabelas são
> criadas pela API ao iniciar (ou por [`deploy/schema.sql`](deploy/schema.sql), gerado dos modelos), os produtos de
> exemplo por `backend/app/seed.py` na primeira execução, e as fotos de exemplo podem ser
> geradas com `local/fotos_exemplo/gerar_fotos.py`.

Fluxo de uma pergunta ao assistente ("Quais itens preciso repor?"):

1. O navegador envia a pergunta para `POST /api/chat` na EC2.
2. A API chama o **Bedrock Agent** (`InvokeAgent`).
3. O modelo de linguagem decide usar a ferramenta `itens_estoque_baixo` e o Bedrock invoca a **Lambda**.
4. A Lambda (dentro da VPC) chama `GET /api/items?low_stock=true` no **IP privado** da EC2.
5. A API consulta o **Aurora** e devolve os itens; o agente monta a resposta em português.

## Estrutura

```
backend/            API FastAPI (um arquivo por serviço AWS)
  app/main.py         rotas da API
  app/db.py           conexão com Aurora (ou SQLite local)
  app/storage.py      Amazon S3
  app/agent.py        Amazon Bedrock Agents (ou modo simulado)
  app/agent_local.py  agente simulado: "LLM" de regras + ciclo de ferramentas do Bedrock
  app/forecast.py     previsão de demanda (média móvel)
  app/guardrails.py   proteções do assistente (entrada e saída)
  app/skus.py         geração automática do código do produto
  app/instance.py     metadados da EC2
  app/seed.py         dados de exemplo (10 itens, 30 dias de histórico)
  tests/              testes de API, Lambda, contrato das ferramentas e conversas do agente
frontend/           React + Vite (Painel, Itens, Assistente IA, Arquitetura AWS)
lambda/             ferramentas do agente (só biblioteca padrão: dá para colar no console)
bedrock/            instruções do agente e action_group.json (fonte única das ferramentas)
local/              PostgreSQL local, subir a API e chat de terminal
deploy/             script de instalação da EC2, nginx, systemd, política IAM e schema.sql (tabelas)
docs/               roteiros da aula, falhas e segurança
```

## Documentação da aula

1. [`docs/ROTEIRO_DEPLOY.md`](docs/ROTEIRO_DEPLOY.md): passo a passo no console da AWS (instrutor)
2. [`docs/ROTEIRO_ALUNOS.md`](docs/ROTEIRO_ALUNOS.md): atividades para os alunos testarem o sistema
3. [`docs/FALHAS_E_SEGURANCA.md`](docs/FALHAS_E_SEGURANCA.md): como derrubar serviços na aula e o que foi feito para não expor chaves
4. [`docs/LIMPEZA.md`](docs/LIMPEZA.md): custos estimados e como apagar tudo no final

## Fase 1: rodar e testar tudo localmente

Localmente o sistema roda **montado como em produção**, trocando só os serviços gerenciados:

| Na AWS | Localmente |
|---|---|
| Aurora PostgreSQL | PostgreSQL 16 local (`pgserver`, sem Docker) |
| S3 | **emulador de S3 (Moto)**: o backend usa o mesmo boto3, só muda o endpoint |
| Bedrock Agent (LLM) | agente simulado (`backend/app/agent_local.py`), "LLM" de regras |
| Lambda | **o mesmo código** (`lambda/agente_estoque/`), com o mesmo evento JSON do Bedrock |
| EC2 + nginx | uvicorn + `vite preview` servindo o build de produção com proxy `/api` |

> MinIO e LocalStack não foram usados: o MinIO deixou de distribuir binários gratuitos e o
> LocalStack exige Docker. O Moto é a base de emulação sobre a qual o LocalStack foi construído.

### Instalação (uma vez, sem instalar nada no sistema: tudo fica em `.venv/`)

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
VIRTUAL_ENV=$PWD/.venv PATH=$PWD/.venv/bin:$PATH .venv/bin/nodeenv -p --node=20.18.1
```

### Rodar

```bash
.venv/bin/python local/rodar.py        # sobe banco + S3 + API + site → http://localhost:4173
```

Telas: **Dashboard** (indicadores e gráficos), **Produtos** (catálogo com fotos), **Cadastro**
(com upload de foto para o S3), **Movimentações**, **Arquitetura AWS** (status ao vivo) e o
**Assistente IA** flutuante em todas as telas (mostra as ferramentas que chamou).

Outros comandos:

```bash
.venv/bin/python local/servicos.py status                  # situação de cada serviço
.venv/bin/python local/servicos.py derrubar banco|s3|agente  # simular falhas (ver docs/FALHAS_E_SEGURANCA.md)
.venv/bin/python local/servicos.py restaurar todos
.venv/bin/python local/chat.py                             # chat pelo terminal
.venv/bin/python local/banco.py psql "select sku, name, quantity from items"
.venv/bin/python local/servicos.py encerrar                # desliga banco e S3
```

### Testes automatizados (42)

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

- **API:** produtos, movimentações, validações, fotos no S3 emulado.
- **Lambda e contrato:** eventos no formato do Bedrock; o `action_group.json` precisa bater com a Lambda.
- **Agente:** conversas completas por `/api/chat`.
- **Falhas:** banco, S3 e agente fora do ar (incluindo o circuit breaker).
- **Segurança:** nenhuma chave no repositório e nenhum detalhe interno nas respostas.

## Fase 2: subir na AWS

Siga [`docs/ROTEIRO_DEPLOY.md`](docs/ROTEIRO_DEPLOY.md). Até configurar o Bedrock, o chat na EC2
continua funcionando no modo simulado. Depois de configurado, `python local/chat.py http://IP-DA-EC2`
repete os mesmos testes contra o agente de verdade.

> ⚠️ Projeto didático: a API **não tem autenticação**. Qualquer pessoa com o IP pode alterar
> o estoque. Restrinja o Security Group ao IP do laboratório e apague tudo depois da aula.
