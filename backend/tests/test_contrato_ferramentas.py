"""O schema do action group (bedrock/action_group.json) e a Lambda precisam combinar.
Se não combinarem, o Bedrock chama uma função/parâmetro que a Lambda não conhece."""
import inspect

from app import agent_local

SCHEMA = agent_local.load_schema()
LAMBDA = agent_local.load_lambda()


def test_mesmas_funcoes_no_schema_e_na_lambda():
    assert {f["name"] for f in SCHEMA["functions"]} == set(LAMBDA.TOOLS)


def test_parametros_batem_com_a_assinatura_da_lambda():
    for fn in SCHEMA["functions"]:
        signature = inspect.signature(LAMBDA.TOOLS[fn["name"]]).parameters
        assert set(fn["parameters"]) == set(signature), fn["name"]
        for name, spec in fn["parameters"].items():
            has_default = signature[name].default is not inspect.Parameter.empty
            assert spec["required"] == (not has_default), f"{fn['name']}.{name}"


def test_limites_do_bedrock():
    # Bedrock Agents (function details): até 5 parâmetros por função; tipos permitidos
    for fn in SCHEMA["functions"]:
        assert len(fn["parameters"]) <= 5, fn["name"]
        assert len(fn["description"]) <= 1200
        for spec in fn["parameters"].values():
            assert spec["type"] in {"string", "number", "integer", "boolean", "array"}
