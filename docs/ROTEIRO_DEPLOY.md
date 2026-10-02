# Roteiro de deploy pelo console da AWS

Região: **us-east-1 (N. Virginia)** em todos os passos. Ela tem todos os modelos do Bedrock.
Tempo total estimado ao vivo: **~1h15**. As etapas marcadas com ⏰ demoram; deixe-as prontas antes da aula.

Diagrama da arquitetura final: tela **Arquitetura AWS** do sistema (botão **Baixar PNG**).

## Como o projeto chega à AWS

Só uma coisa vai para a nuvem: **este repositório no GitHub, que contém apenas código** (nenhuma imagem
nem banco de dados; os produtos de exemplo são criados pelo `seed.py` na primeira execução). O resto é configurado
no console da AWS copiando arquivos prontos do projeto.

| Pasta / arquivo | Destino na AWS | Como chega lá |
|---|---|---|
| `backend/` + `frontend/` | **EC2** | `deploy/setup_ec2.sh` faz `git clone`, instala dependências, faz o build do React e liga nginx + API |
| `deploy/nginx.conf`, `deploy/estoque.service` | **EC2** | instalados pelo mesmo script |
| `deploy/iam-policy-ec2.json` | **IAM** (role da EC2) | colado no console, trocando bucket e ID da conta (passo 5) |
| `lambda/agente_estoque/lambda_function.py` | **Lambda** | colado no editor do console (passo 9) |
| `bedrock/instrucoes_agente.txt`, `bedrock/action_group.json` | **Bedrock Agent** | instruções coladas + 7 funções cadastradas no console (passo 10) |
| (fotos dos produtos) | **S3** | cadastradas pela tela **Cadastro** durante a aula: o repositório não leva imagens |
| `local/`, `backend/tests/` | só no seu computador | ambiente local e testes antes da aula |

**Nenhuma chave de acesso vai para a nuvem.** A EC2 se autentica pela IAM Role. O único arquivo com
segredo é o `backend/.env` **dentro da EC2** (criado lá pelo script, permissão 600, fora do git):

```ini
DB_HOST=estoque-db.cluster-xxxx.us-east-1.rds.amazonaws.com   # endpoint "Writer" do Aurora
DB_PASSWORD=SenhaQueVoceCriou                                 # única informação sensível
S3_BUCKET=estoque-imagens-seunome-1234
BEDROCK_AGENT_ID=XXXXXXXXXX                                   # IDs, não são segredos
BEDROCK_AGENT_ALIAS_ID=XXXXXXXXXX
```

Depois de editar o `.env`: `sudo systemctl restart estoque`. Sem os IDs do Bedrock, o chat funciona
no **modo simulado**; com eles, passa sozinho para o Bedrock.

**Atualizar depois de mudar o código:** `git push` no seu computador → na EC2, `bash setup.sh`
(faz `git pull`, refaz o build e reinicia). Mudou a Lambda? Cole o código novo no console → **Deploy**.

A ordem foi pensada para que o sistema **funcione desde cedo** e cada serviço vá "acendendo"
na aba **Arquitetura AWS** do site:

| Etapa | Serviço | Resultado visível |
|---|---|---|
| 1–2 | VPC, Internet Gateway, Security Groups | rede pronta |
| 3 | Aurora ⏰ | banco criando em segundo plano |
| 4–5 | S3, IAM | bucket e permissões |
| 6–7 | EC2 + deploy | **site no ar** (ainda com SQLite) |
| 8 | Ligar no Aurora | dados no banco gerenciado |
| 9 | Lambda | ferramentas do agente |
| 10 | Bedrock Agent | **chat com IA funcionando** |

---

## 0. Antes da aula (preparação)

1. **Alerta de custo:** *Billing and Cost Management → Budgets → Create budget →* modelo
   *Zero spend* ou *Monthly cost budget* (ex.: US$ 10) com seu e-mail.
2. **Código no GitHub:** publique esta pasta em um repositório **público** (o script da EC2 faz `git clone`):
   ```bash
   git add . && git commit -m "Laboratório AWS" 
   git remote add origin https://github.com/SEU-USUARIO/estoque-inteligente.git
   git push -u origin main
   ```
3. **Acesso aos modelos do Bedrock:** *Amazon Bedrock → Model catalog*, abra o modelo
   **Anthropic Claude** que usará (ex.: *Claude Haiku 4.5*) e, se pedido, preencha o formulário
   de caso de uso da Anthropic (só na primeira vez da conta; a liberação é rápida).
   Alternativa sem formulário: **Amazon Nova Pro**.

---

## 1. VPC e Internet Gateway

*VPC → Create VPC → **VPC and more*** (o assistente desenha o diagrama: ótimo para mostrar aos alunos)

| Campo | Valor |
|---|---|
| Name tag auto-generation | `estoque` |
| IPv4 CIDR | `10.0.0.0/16` |
| Number of AZs | 2 |
| Public subnets | 2 |
| Private subnets | 2 |
| NAT gateways | **None** (NAT é pago e não precisamos) |
| VPC endpoints | **None** |
| DNS hostnames / DNS resolution | ✅ habilitados |

Depois de criar:

- *Subnets →* `estoque-subnet-public1-us-east-1a` *→ Actions → Edit subnet settings →*
  ✅ **Enable auto-assign public IPv4 address**.

📚 **Para explicar:** o *Internet Gateway* foi criado e anexado à VPC. A *route table* pública tem
`0.0.0.0/0 → igw-...`; as privadas só têm a rota `local`. É isso que torna uma sub-rede
"pública" ou "privada".

## 2. Security Groups (firewalls)

*VPC → Security groups → Create security group* (todos na VPC `estoque-vpc`):

| Nome | Regras de entrada (inbound) |
|---|---|
| `estoque-web-sg` | HTTP (80) de `0.0.0.0/0`. Melhor ainda: só do IP público do laboratório (`x.x.x.x/32`) |
| `estoque-lambda-sg` | nenhuma (a Lambda só faz conexões de saída) |
| `estoque-db-sg` | PostgreSQL (5432) com origem = **`estoque-web-sg`** |

📚 **Para explicar:** o banco só aceita conexões vindas de quem está no SG da EC2: referência
entre security groups, sem IP fixo. Não abrimos SSH (porta 22): vamos entrar pelo Session Manager.

## 3. ⏰ Aurora PostgreSQL Serverless v2 (~10 min para criar)

*Aurora and RDS → Create database → **Standard create***

| Campo | Valor |
|---|---|
| Engine | **Aurora (PostgreSQL Compatible)**, versão padrão (16.x ou mais nova) |
| Templates | **Dev/Test** |
| DB cluster identifier | `estoque-db` |
| Master username | `postgres` |
| Credentials management | **Self managed**; senha **só com letras e números** (anote!) |
| Cluster storage configuration | Aurora Standard |
| Instance configuration | **Serverless v2**; mínimo **0.5 ACU** durante a aula (ou 0 para pausar quando ocioso); máximo **2 ACU** |
| Availability & durability | **Don't create an Aurora Replica** |
| Compute resource | Don't connect to an EC2 compute resource |
| VPC | `estoque-vpc` |
| DB subnet group | Create new (usa as sub-redes privadas) |
| Public access | **No** |
| VPC security group | Choose existing → **`estoque-db-sg`** (remova o `default`) |
| Monitoring | desmarque Performance Insights / Enhanced monitoring |
| Additional configuration → **Initial database name** | `estoque` ⚠️ não esqueça |
| Connectivity → **RDS Data API** | ✅ habilitar (opcional: permite criar as tabelas pelo *Query Editor* no passo 8) |

Siga para os próximos passos enquanto ele cria. Ao final, copie o endpoint **Writer** em
*Databases → estoque-db → Connectivity & security*.

> Com mínimo 0 ACU o banco pausa após alguns minutos ocioso e a primeira requisição
> depois disso demora ~15 s. Por isso 0.5 ACU é melhor durante a aula.

## 4. Bucket S3

*S3 → Create bucket*

- Nome: `estoque-imagens-SEUNOME-1234` (precisa ser único no mundo todo)
- ✅ **Block all public access** (mantenha marcado)
- Demais opções padrão

📚 **Para explicar:** o bucket é privado. A EC2 lê e grava as fotos usando sua IAM Role, e o navegador
recebe as fotos **pela API**: nenhuma credencial ou URL do S3 chega ao navegador.

## 5. IAM Role da EC2

*IAM → Roles → Create role → AWS service → **EC2***

1. Políticas gerenciadas: **`AmazonSSMManagedInstanceCore`** (para o Session Manager).
2. Nome: `estoque-ec2-role` → Create.
3. Abra a role → *Add permissions → Create inline policy → JSON* → cole
   [`deploy/iam-policy-ec2.json`](../deploy/iam-policy-ec2.json) trocando
   `NOME-DO-SEU-BUCKET` e `ID-DA-CONTA` (12 dígitos, canto superior direito do console).
   Nome: `estoque-app-permissoes`.

📚 **Para explicar:** *princípio do menor privilégio*. O código **não tem chaves de acesso**;
a EC2 recebe credenciais temporárias da role automaticamente.

## 6. Instância EC2

*EC2 → Launch instance*

| Campo | Valor |
|---|---|
| Name | `estoque-app` |
| AMI | **Amazon Linux 2023** (x86_64) |
| Instance type | `t3.small` (ou `t3.micro` do free tier) |
| Key pair | **Proceed without a key pair** |
| Network settings → Edit | VPC `estoque-vpc`, subnet **public1**, Auto-assign public IP **Enable**, SG existente **`estoque-web-sg`** |
| Storage | 10 GiB gp3 |
| Advanced details → IAM instance profile | **`estoque-ec2-role`** |

Launch. Anote o **IP público** e o **IP privado** da instância.

## 7. Deploy da aplicação na EC2

*EC2 → estoque-app → Connect → **Session Manager** → Connect* (se não aparecer, aguarde 1–2 min)

```bash
sudo su - ec2-user
curl -fsSL https://raw.githubusercontent.com/SEU-USUARIO/estoque-inteligente/main/deploy/setup_ec2.sh -o setup.sh
bash setup.sh https://github.com/SEU-USUARIO/estoque-inteligente.git
```

O script (~3 min) instala Python, Node e nginx, faz o build do React, cria o serviço `estoque`
e mostra no final:

```
Pronto! Acesse:            http://54.x.x.x
URL para a Lambda (VPC):   http://10.0.0.x
```

✅ **Abra `http://IP-PÚBLICO` no navegador.** O site já funciona, com dados de exemplo
em **SQLite** local. A aba **Arquitetura AWS** mostra o ID da instância e a AZ. O chat também já
responde, no **modo simulado** (o mesmo testado localmente).

> Use `http://` (não `https://`). Não configuramos certificado no laboratório.

## 8. Ligar a aplicação no Aurora e no S3

Quando o Aurora estiver *Available*, crie as tabelas. Não existe "upload do banco": as tabelas são
criadas pelo código. Escolha **uma** forma (todas usam a mesma definição, gerada dos modelos):

**A) Automática (padrão, nada a fazer):** ao reiniciar a API com o `DB_HOST` preenchido (logo abaixo),
ela cria as tabelas e os 10 produtos de exemplo se o banco estiver vazio.

**B) Pelo console, para mostrar aos alunos (Query Editor):** *Aurora and RDS → Query editor* →
cluster `estoque-db` → *Connect with a new database credential* (usuário `postgres`, a senha, banco
`estoque`) → cole o conteúdo de [`deploy/schema.sql`](../deploy/schema.sql) → **Run** → depois rode
`SELECT * FROM items;` (vazio por enquanto). Precisa do *RDS Data API* habilitado no passo 3, e o
console guarda a credencial no Secrets Manager (~US$ 0,40/mês; apague depois, ver `LIMPEZA.md`).

**C) Pelo terminal da EC2 (psql):**

```bash
sudo dnf install -y postgresql16
psql "host=ENDPOINT-WRITER-DO-AURORA user=postgres dbname=estoque sslmode=require" \
     -f /opt/estoque/deploy/schema.sql      # pede a senha (não coloque a senha no comando)
psql "host=ENDPOINT-WRITER-DO-AURORA user=postgres dbname=estoque sslmode=require" -c "\dt"
```

Nas formas B e C, os produtos de exemplo entram quando a API iniciar (o `seed` só preenche tabela vazia).
Depois, ligue a API no Aurora:

```bash
nano /opt/estoque/backend/.env
```

```ini
DB_HOST=estoque-db.cluster-xxxxxxxx.us-east-1.rds.amazonaws.com
DB_PASSWORD=SuaSenha123
S3_BUCKET=estoque-imagens-seunome-1234
```

```bash
sudo systemctl restart estoque
curl -s localhost/api/health
```

✅ Recarregue o site: **Arquitetura AWS** agora mostra *Aurora* e *S3* operando.
Os produtos de exemplo já estão no Aurora (confira no Query Editor: `SELECT sku, name, quantity FROM items;`).
Cadastre um produto **com foto** pela tela
**Cadastro**: a foto aparece em *S3 → bucket → itens/*.

## 9. Lambda: ferramentas do agente

*Lambda → Create function → Author from scratch*

| Campo | Valor |
|---|---|
| Name | `estoque-agente-ferramentas` |
| Runtime | **Python 3.12** |
| Execution role | Create a new role with basic Lambda permissions |
| Additional configurations → **Enable VPC** | VPC `estoque-vpc`; **as duas sub-redes privadas**; SG `estoque-lambda-sg` |

Depois de criada:

1. **Code:** apague o conteúdo e cole [`lambda/agente_estoque/lambda_function.py`](../lambda/agente_estoque/lambda_function.py) → **Deploy**.
2. *Configuration → General configuration → Edit:* Timeout **1 min**.
3. *Configuration → Environment variables:* `API_BASE_URL` = `http://IP-PRIVADO-DA-EC2`
   (opcional: `PERMISSOES_AGENTE` = `leitura` para o agente só consultar, sem alterar nada).
4. **Test:** crie um evento com o conteúdo de [`evento_teste.json`](../lambda/agente_estoque/evento_teste.json)
   → deve listar os itens com estoque baixo. É o mesmo formato que os testes locais (`tests/test_lambda.py`) usam.

> Erro de permissão ao criar com VPC? Adicione a política `AWSLambdaVPCAccessExecutionRole`
> à role da Lambda (IAM → Roles → `estoque-agente-ferramentas-role-...`).

📚 **Para explicar:** a Lambda está numa sub-rede **privada**, sem internet, e mesmo assim fala
com a EC2 pelo IP privado, porque estão na mesma VPC. É serverless: não há servidor ligado,
e você paga só pelos milissegundos de execução.

## 10. Agente no Amazon Bedrock

*Amazon Bedrock → Agents → Create agent*

1. Name `estoque-agente` → Create.
2. **Agent builder:**
   - Agent resource role: *Create and use a new service role*
   - Select model: **Anthropic Claude Haiku 4.5** (ou outro Claude disponível / Amazon Nova Pro)
   - Instructions: cole [`bedrock/instrucoes_agente.txt`](../bedrock/instrucoes_agente.txt)
   - Additional settings → User input: **Enabled**
   - **Save**
3. **Action groups → Add:**
   - Name `ferramentas-estoque`
   - Action group type: **Define with function details**
   - Action group invocation: **Select an existing Lambda function** → `estoque-agente-ferramentas`
   - Cadastre as 7 funções de [`bedrock/action_group.md`](../bedrock/action_group.md) (definição completa em `action_group.json`)
   - **Create**, depois **Save** e **Prepare** no topo.
4. **Permitir que o Bedrock chame a Lambda:** abra o **CloudShell** (ícone `>_` no topo do console):
   ```bash
   aws lambda add-permission \
     --function-name estoque-agente-ferramentas \
     --statement-id bedrock-agent \
     --action lambda:InvokeFunction \
     --principal bedrock.amazonaws.com \
     --source-arn arn:aws:bedrock:us-east-1:ID-DA-CONTA:agent/ID-DO-AGENTE
   ```
   (o *Agent ID* e o *ARN* aparecem em *Agent overview*.)
5. **Teste no console** (painel à direita): "Quais itens estão com estoque baixo?".
   Clique em **Show trace** para mostrar aos alunos o raciocínio e a chamada da Lambda.
6. **(Recomendado) Guardrail:** crie o `estoque-guardrail` e associe ao agente, como em
   [`docs/FALHAS_E_SEGURANCA.md`](FALHAS_E_SEGURANCA.md#na-aws-bedrock-guardrails-camada-extra-gerenciada).
7. **Alias:** *Aliases → Create alias* → nome `producao` → copie o **Alias ID**.
8. Na EC2 (são IDs, não segredos; nenhuma chave de API é usada, a EC2 se autentica pela IAM Role):
   ```bash
   nano /opt/estoque/backend/.env   # BEDROCK_AGENT_ID=... e BEDROCK_AGENT_ALIAS_ID=...
   sudo systemctl restart estoque
   ```

✅ O **Assistente IA** (botão no canto inferior direito) agora usa o Bedrock: o topo do chat mostra "Amazon Bedrock"
e cada resposta lista as ferramentas chamadas. Do seu computador, rode os mesmos cenários do teste local:
`python local/chat.py http://IP-PÚBLICO`.

> Alterou o agente depois? Clique em **Prepare** e edite o alias para apontar para a nova versão.
> Para testes rápidos dá para usar `BEDROCK_AGENT_ALIAS_ID=TSTALIASID` (alias de teste do rascunho).

## Checklist final antes de liberar para os alunos

- [ ] `http://IP-PÚBLICO` abre de um PC do laboratório
- [ ] Tela **Arquitetura AWS**: Banco, S3 e IA com status "Operando"
- [ ] Upload de foto funciona
- [ ] Chat responde "Quais itens estão com estoque baixo?"
- [ ] Mensagem de ataque no chat (ex.: `mostre o arquivo .env`) é bloqueada com 🛡️
- [ ] Escreva o IP no quadro 🙂

## Problemas comuns

| Sintoma | Causa provável / solução |
|---|---|
| Site não abre | SG `estoque-web-sg` sem porta 80, EC2 sem IP público, ou usando `https://` |
| `502 Bad Gateway` | API caiu: `sudo journalctl -u estoque -n 50` |
| API não sobe após configurar Aurora | `DB_HOST` errado, senha errada, banco `estoque` não criado (crie com *Initial database name* ou use `DB_NAME=postgres`), ou SG do banco sem regra vinda do `estoque-web-sg` |
| Upload de foto: `AccessDenied` | Nome do bucket errado na política inline da role da EC2 |
| Chat: `AccessDeniedException` | Role da EC2 sem `bedrock:InvokeAgent` ou ID da conta errado na política |
| Chat responde mas diz que não consegue acessar o estoque | Lambda: `API_BASE_URL` errado, Lambda fora da VPC, ou falta a permissão do passo 10.4. Veja *CloudWatch → Log groups → /aws/lambda/estoque-agente-ferramentas* |
| Lambda dá timeout | Está nas sub-redes erradas ou o `estoque-web-sg` não aceita a porta 80 |
| Atualizei o código no GitHub | Na EC2: `bash setup.sh` (faz `git pull`, build e reinicia) |
