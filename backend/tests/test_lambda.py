"""A Lambda recebendo eventos no formato exato do Bedrock (todos os valores como string)."""
from app import agent_local

LAMBDA = agent_local.load_lambda()


def invoke(function, **params):
    event = {
        "messageVersion": "1.0",
        "agent": {"name": "estoque-agente", "id": "TESTE", "alias": "TSTALIASID", "version": "DRAFT"},
        "sessionId": "teste",
        "inputText": "teste",
        "actionGroup": "ferramentas-estoque",
        "function": function,
        "parameters": [{"name": k, "type": "string", "value": str(v)} for k, v in params.items()],
    }
    response = LAMBDA.lambda_handler(event, None)
    assert response["messageVersion"] == "1.0"
    assert response["response"]["actionGroup"] == "ferramentas-estoque"
    assert response["response"]["function"] == function
    return response["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]


def test_consultas(server):
    assert "MS-002" in invoke("itens_estoque_baixo")
    assert "itens cadastrados" in invoke("resumo_estoque")
    assert invoke("consultar_estoque", termo="headset").startswith("HD-006 | Headset")
    assert invoke("consultar_estoque", termo="xyzxyz").startswith("Nenhum item")
    assert len(invoke("consultar_estoque").splitlines()) >= 10


def test_cadastrar_e_atualizar_com_valores_em_texto(server, item):
    out = invoke("cadastrar_item", nome="Item Lambda", preco="1.299,90", quantidade="3", estoque_minimo="4")
    sku = out.split("código ")[1].split(":")[0]
    assert sku.startswith("GER-")                     # categoria padrão "Geral"
    assert item(sku)["unit_price"] == 1299.90 and item(sku)["min_quantity"] == 4

    out = invoke("atualizar_item", sku=sku.lower(), preco="10.5", estoque_minimo="2")
    assert out.startswith("Item atualizado")
    assert item(sku)["unit_price"] == 10.5 and item(sku)["min_quantity"] == 2
    assert "informe ao menos um campo" in invoke("atualizar_item", sku=sku)


def test_movimentacoes(server, item):
    before = item("WC-009")["quantity"]
    assert "Estoque atual" in invoke("registrar_movimentacao", sku="WC-009", tipo="saída", quantidade="2")
    assert item("WC-009")["quantity"] == before - 2
    assert "insuficiente" in invoke("registrar_movimentacao", sku="WC-009", tipo="saida", quantidade="999")
    assert "tipo deve ser" in invoke("registrar_movimentacao", sku="WC-009", tipo="troca", quantidade="1")
    assert "Nenhum item com SKU" in invoke("registrar_movimentacao", sku="ZZ-999", tipo="saida", quantidade="1")


def test_previsao_e_funcao_inexistente(server):
    assert "Previsão para SSD" in invoke("prever_demanda", sku="SS-008")
    assert "não existe" in invoke("apagar_tudo")
