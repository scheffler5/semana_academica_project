# Action Group `ferramentas-estoque`

A definição oficial está em [`action_group.json`](action_group.json). É o mesmo arquivo que o
agente simulado e os testes locais usam, então o que passou nos testes é o que vai para o console.

No console do Bedrock, ao criar o Action Group escolha **Define with function details**
e cadastre as 7 funções abaixo, com nomes **exatamente** iguais aos da Lambda.
(Descrições completas: copie do JSON.)

| Função | Parâmetros (tipo, obrigatório?) |
|---|---|
| `consultar_estoque` | `termo` (string, não) |
| `itens_estoque_baixo` | nenhum |
| `resumo_estoque` | nenhum |
| `cadastrar_item` | `nome` (string, sim) · `preco` (number, sim) · `quantidade` (integer, não) · `categoria` (string, não) · `estoque_minimo` (integer, não). O SKU é gerado pelo sistema |
| `atualizar_item` | `sku` (string, sim) · `preco` (number, não) · `estoque_minimo` (integer, não) · `nome` (string, não) |
| `registrar_movimentacao` | `sku` (string, sim) · `tipo` (string, sim) · `quantidade` (integer, sim) · `observacao` (string, não) |
| `prever_demanda` | `sku` (string, sim) |

> Não ative **Enable confirmation**: o frontend não implementa essa etapa.
