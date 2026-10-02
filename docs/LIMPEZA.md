# Custos e limpeza

## Quanto custa (estimativa, us-east-1)

Valores aproximados; confira sempre na [calculadora da AWS](https://calculator.aws).

| Recurso | Como cobra | Estimativa |
|---|---|---|
| EC2 `t3.small` | por hora ligada | ~US$ 0,02/h (t3.micro pode entrar no free tier) |
| IPv4 público | por hora | ~US$ 0,005/h |
| S3 | GB armazenado + requisições | centavos (fotos e os dois arquivos JSON de dados) |
| Lambda | por requisição/ms | free tier cobre |
| Bedrock (Claude Haiku) | por token | centavos por aula (cada pergunta ≈ alguns milhares de tokens) |

Sem Aurora/RDS neste laboratório, o custo fica ainda mais baixo. Uma aula de 4 horas com tudo
ligado custa poucos dólares. O perigo é **esquecer recursos ligados**.

## Apagar tudo (nesta ordem)

1. **Bedrock:** *Agents →* `estoque-agente` → Delete; *Guardrails →* `estoque-guardrail` → Delete
2. **Lambda:** `estoque-agente-ferramentas` → Delete
3. **EC2:** `estoque-app` → *Instance state → Terminate*
4. **S3:** esvazie (*Empty*) e apague o bucket de imagens/dados
5. **VPC:** *Your VPCs →* `estoque-vpc` → *Delete VPC* (apaga sub-redes, IGW, route tables e SGs juntos)
   > Se reclamar de *network interfaces* em uso: são as ENIs da Lambda, que a AWS libera em até
   > ~20–40 min depois de apagar a função. Espere e tente de novo.
6. **IAM:** roles `estoque-ec2-role`, `estoque-agente-ferramentas-role-*` e `AmazonBedrockExecutionRoleForAgents_*`
7. **CloudWatch Logs:** log groups `/aws/lambda/estoque-*`
8. **Billing → Bills** no dia seguinte, para conferir que nada ficou cobrando.

> Se em algum momento você criou um banco Aurora de teste e ainda não apagou: *RDS → Databases* →
> apague a **instância** e depois o **cluster**; e o **DB subnet group** em *RDS → Subnet groups*.
