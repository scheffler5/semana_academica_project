"""API REST (o que o site e a Lambda usam)."""


def test_health(api):
    body = api.get("/api/health").json()
    assert body["status"] == "ok"
    services = body["services"]
    assert services["s3"]["status"] == "ok"
    assert services["agent"]["status"] == "simulated"
    assert "database" not in services and "sagemaker" not in services
    assert body["agent_mode"] == "simulado"


def test_dados_de_exemplo(api):
    d = api.get("/api/dashboard").json()
    assert d["total_items"] >= 10
    assert {"MS-002", "SS-008", "CD-010"} <= {i["sku"] for i in d["low_stock"]}


def test_crud_e_movimentacoes(api):
    res = api.post("/api/items", json={"sku": "api-01", "name": "Item de API", "quantity": 10, "unit_price": 5})
    assert res.status_code == 201
    created = res.json()
    assert created["sku"] == "API-01"

    assert api.post("/api/items", json={"sku": "API-01", "name": "dup"}).status_code == 409
    assert api.get("/api/items", params={"search": "item de api"}).json()[0]["id"] == created["id"]

    res = api.post(f"/api/items/{created['id']}/movements", json={"type": "saida", "quantity": 4})
    assert res.json()["quantity"] == 6
    res = api.post(f"/api/items/{created['id']}/movements", json={"type": "saida", "quantity": 99})
    assert res.status_code == 400 and "insuficiente" in res.json()["message"]
    res = api.post(f"/api/items/{created['id']}/movements", json={"type": "entrada", "quantity": 1})
    assert res.json()["quantity"] == 7
    assert len(api.get(f"/api/items/{created['id']}/movements").json()) == 3  # inicial + 2

    res = api.put(f"/api/items/{created['id']}", json={"unit_price": 7.5, "min_quantity": 8})
    assert res.json()["unit_price"] == 7.5 and res.json()["low_stock"] is True

    assert api.delete(f"/api/items/{created['id']}").status_code == 204
    assert api.get(f"/api/items/{created['id']}").status_code == 404


def test_validacao(api):
    assert api.post("/api/items", json={"sku": "", "name": "x"}).status_code == 422
    assert api.post("/api/items", json={"sku": "N-1", "name": "x", "unit_price": -1}).status_code == 422
    item_id = api.get("/api/items").json()[0]["id"]
    res = api.post(f"/api/items/{item_id}/movements", json={"type": "roubo", "quantity": 1})
    assert res.status_code == 422


def test_previsao(api, item):
    forecast = api.get(f"/api/items/{item('CB-005')['id']}/forecast").json()
    assert len(forecast["history_14_days"]) == 14
    assert forecast["days_until_out"] > 0


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def test_foto_no_s3(api, item):
    item_id = item("NB-001")["id"]
    res = api.post(f"/api/items/{item_id}/image", files={"file": ("foto.png", PNG, "image/png")})
    assert res.status_code == 200
    url = res.json()["image_url"]
    assert url.startswith(f"/api/items/{item_id}/image?v=")   # passa pela API, sem URL assinada
    photo = api.get(url)
    assert photo.content == PNG and photo.headers["content-type"] == "image/png"

    from app import s3client
    from conftest import BUCKET
    keys = [o["Key"] for o in s3client._s3.list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert any(k.startswith(f"itens/{item_id}/") for k in keys)


def test_foto_invalida(api, item):
    item_id = item("NB-001")["id"]
    # Content-Type diz imagem, mas o conteúdo não é: recusado pela assinatura dos bytes
    res = api.post(f"/api/items/{item_id}/image", files={"file": ("x.png", b"<script>", "image/png")})
    assert res.status_code == 400
    res = api.post(f"/api/items/{item_id}/image", files={"file": ("big.png", PNG + b"0" * 5_300_000, "image/png")})
    assert res.status_code == 413
    assert api.get(f"/api/items/{item('MN-004')['id']}/image").status_code == 404


def test_dashboard_series(api):
    d = api.get("/api/dashboard").json()
    assert len(d["daily"]) == 14
    assert d["by_category"][0]["value"] >= d["by_category"][-1]["value"]
    assert api.get("/api/categories").json()


def test_sku_gerado_automaticamente(api):
    preview = api.get("/api/items/next-sku", params={"category": "Ferramentas"}).json()["sku"]
    assert preview == "FER-001"
    first = api.post("/api/items", json={"name": "Martelo", "category": "Ferramentas", "unit_price": 30}).json()
    second = api.post("/api/items", json={"name": "Alicate", "category": "Ferramentas", "unit_price": 25}).json()
    assert (first["sku"], second["sku"]) == ("FER-001", "FER-002")
    assert api.get("/api/items/next-sku", params={"category": "Ferramentas"}).json()["sku"] == "FER-003"
    # acentos e categorias curtas
    assert api.post("/api/items", json={"name": "x", "category": "Óculos", "unit_price": 1}).json()["sku"] == "OCU-001"
    assert api.post("/api/items", json={"name": "y", "category": "TI", "unit_price": 1}).json()["sku"] == "TIX-001"
    # SKU manual inválido é recusado
    assert api.post("/api/items", json={"sku": "a b'c", "name": "z", "unit_price": 1}).status_code == 422
