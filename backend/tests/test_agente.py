"""Conversas completas pelo POST /api/chat (agente simulado -> Lambda -> API -> banco).

Cada teste confere: a resposta, QUAIS ferramentas o agente usou e o efeito real no banco.
Os mesmos cenários servem de roteiro para testar o agente do Bedrock depois.
"""
from conftest import functions


# ------------------------------------------------------------- consultas

def test_estoque_baixo(chat):
    r = chat("Quais itens estão com estoque baixo?")
    assert functions(r) == ["itens_estoque_baixo"]
    assert "MS-002" in r["answer"] and "SS-008" in r["answer"]
    assert r["mode"] == "simulado"


def test_quantidade_por_nome_no_plural(chat):
    r = chat("Quantos mouses temos?")
    assert functions(r) == ["consultar_estoque"]
    assert r["tools_used"][0]["parameters"] == {"termo": "mouse"}
    assert "MS-002" in r["answer"]


def test_preco(chat):
    r = chat("Qual o preço do monitor?")
    assert "MN-004" in r["answer"] and "R$ 899.00" in r["answer"]


def test_resumo(chat):
    r = chat("Qual o valor total do estoque?")
    assert functions(r) == ["resumo_estoque"]
    assert "valor total" in r["answer"]


def test_item_inexistente(chat):
    r = chat("Quantos unicórnios temos?")
    assert "Não encontrei" in r["answer"]


def test_memoria_da_sessao(chat):
    chat("Quantos teclados temos?")
    r = chat("E qual o preço dele?")
    assert r["tools_used"][0]["parameters"] == {"termo": "TC-003"}
    assert "TC-003" in r["answer"]


def test_ajuda(chat):
    r = chat("oi")
    assert functions(r) == [] and "Exemplos" in r["answer"]


# ------------------------------------------------------------- cadastro e alteração

def test_cadastrar_item_gera_o_codigo(chat, item):
    r = chat("Cadastre o produto Fone Bluetooth JBL, preço 199,90, 30 unidades, categoria Áudio")
    assert functions(r) == ["cadastrar_item"]
    assert r["tools_used"][0]["parameters"] == {
        "nome": "Fone Bluetooth JBL", "preco": "199,90", "quantidade": "30", "categoria": "Áudio",
    }
    assert "código AUD-001" in r["answer"]          # o sistema gerou o SKU
    created = item("AUD-001")
    assert (created["name"], created["unit_price"], created["quantity"], created["category"]) == \
        ("Fone Bluetooth JBL", 199.90, 30, "Áudio")

    r = chat("Quantas unidades dele temos?")          # o agente lembra do código criado
    assert r["tools_used"][0]["parameters"] == {"termo": "AUD-001"}

    r = chat("cadastre um novo item chamado Fone USB por R$ 89,90, categoria Áudio")
    assert "código AUD-002" in r["answer"]


def test_cadastro_incompleto_pede_dados(chat):
    r = chat("Cadastre um novo item chamado mesa")
    assert functions(r) == []
    assert "preciso de" in r["answer"]


def test_alterar_preco_por_sku(chat, item):
    r = chat("Altere o preço do MS-002 para 99,90")
    assert functions(r) == ["atualizar_item"]
    assert item("MS-002")["unit_price"] == 99.90


def test_alterar_minimo_por_nome(chat, item):
    r = chat("Mude o estoque mínimo do SSD para 10")
    assert functions(r) == ["consultar_estoque", "atualizar_item"]  # descobre o SKU antes
    assert r["tools_used"][1]["parameters"] == {"sku": "SS-008", "estoque_minimo": "10"}
    assert item("SS-008")["min_quantity"] == 10


# ------------------------------------------------------------- movimentações

def test_registrar_venda(chat, item):
    before = item("HD-006")["quantity"]
    r = chat("Registre a venda de 2 headsets")
    assert functions(r) == ["consultar_estoque", "registrar_movimentacao"]
    assert r["tools_used"][1]["parameters"]["tipo"] == "saida"
    assert item("HD-006")["quantity"] == before - 2


def test_registrar_entrada(chat, item):
    before = item("CB-005")["quantity"]
    r = chat("Chegaram 50 cabos HDMI do fornecedor")
    assert r["tools_used"][-1]["parameters"]["tipo"] == "entrada"
    assert item("CB-005")["quantity"] == before + 50


def test_venda_maior_que_estoque(chat, item):
    before = item("CD-010")["quantity"]
    r = chat("Registre a venda de 500 unidades do CD-010")
    assert "insuficiente" in r["answer"]
    assert item("CD-010")["quantity"] == before


def test_item_ambiguo_pergunta_qual(chat, api):
    api.post("/api/items", json={"sku": "CB-099", "name": "Cabo USB-C", "quantity": 5, "unit_price": 20})
    r = chat("Registre a venda de 1 cabo")
    assert functions(r) == ["consultar_estoque"]
    assert "mais de um item" in r["answer"] and "CB-005" in r["answer"] and "CB-099" in r["answer"]


# ------------------------------------------------------------- previsão de demanda (média móvel)

def test_previsao(chat):
    r = chat("Em quantos dias o SSD vai acabar?")
    assert functions(r) == ["consultar_estoque", "prever_demanda"]
    assert "Previsão para SSD" in r["answer"]
