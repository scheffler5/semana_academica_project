"""Previsão de demanda por média móvel.

Somamos as saídas dos últimos 7 dias e assumimos que os próximos 7 dias serão parecidos.
Com isso estimamos em quantos dias o item acaba. Simples, explicável e sem custo extra.
"""
from datetime import datetime, timedelta

from .store import utcnow

WINDOW_DAYS = 14


def daily_outflow(movements: list, days: int = WINDOW_DAYS) -> list:
    """Lista com a quantidade que saiu em cada um dos últimos `days` dias (mais antigo primeiro)."""
    today = utcnow().date()
    start = today - timedelta(days=days - 1)
    buckets = [0] * days
    for m in movements:
        if m["type"] != "saida":
            continue
        d = datetime.fromisoformat(m["created_at"]).date()
        idx = (d - start).days
        if 0 <= idx < days:
            buckets[idx] += m["quantity"]
    return buckets


def forecast_item(item: dict, movements: list) -> dict:
    history = daily_outflow(movements)
    next_7_days = float(sum(history[-7:]))  # média móvel: a última semana se repete
    daily = next_7_days / 7
    days_until_out = round(item["quantity"] / daily, 1) if daily > 0 else None

    if item["quantity"] == 0:
        recommendation = f"Item esgotado! Demanda prevista de {next_7_days:g} unidades nos próximos 7 dias."
    elif days_until_out is None:
        recommendation = "Sem saídas recentes: não há previsão de ruptura."
    elif days_until_out <= 7:
        recommendation = f"Repor com urgência: deve acabar em cerca de {days_until_out} dias."
    elif days_until_out <= 14:
        recommendation = f"Planejar reposição: estoque para cerca de {days_until_out} dias."
    else:
        recommendation = f"Estoque confortável para cerca de {days_until_out} dias."

    return {
        "sku": item["sku"],
        "name": item["name"],
        "quantity": item["quantity"],
        "history_14_days": history,
        "predicted_next_7_days": next_7_days,
        "predicted_daily": round(daily, 2),
        "days_until_out": days_until_out,
        "recommendation": recommendation,
    }
