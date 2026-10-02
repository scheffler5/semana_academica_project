import { useCallback, useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Boxes, DollarSign, Layers, ShoppingCart, TrendingDown } from "lucide-react";
import { api, brl, brlCompact, dateTime, num } from "../api.js";
import { CategoryBars, MovementsChart } from "../charts/charts.jsx";
import { ErrorState, ItemImage, PageHeader, Skeleton, StockBadge, StockLevel } from "../components/ui.jsx";
import { useApp, useOnStockChange } from "../context.jsx";

function Kpi({ icon: Icon, label, value, hint, tone }) {
  return (
    <div className="card kpi">
      <div className={`kpi-icon ${tone || ""}`}><Icon size={20} /></div>
      <div>
        <span className="kpi-label">{label}</span>
        <strong className="kpi-value">{value}</strong>
        {hint && <span className="kpi-hint">{hint}</span>}
      </div>
    </div>
  );
}

export default function Dashboard({ onNavigate }) {
  const { openItem } = useApp();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api.dashboard().then((d) => { setData(d); setError(null); }).catch(setError);
  }, []);
  useEffect(load, [load]);
  useOnStockChange(load);

  if (error && !data) return <ErrorState error={error} onRetry={load} />;

  const delta = data && data.sold_prev_7d ? ((data.sold_7d - data.sold_prev_7d) / data.sold_prev_7d) * 100 : null;

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Visão geral do estoque em tempo real" />
      {error && <ErrorState error={error} onRetry={load} compact />}

      <section className="kpis">
        {!data ? [1, 2, 3, 4].map((i) => <div key={i} className="card kpi"><Skeleton height={56} /></div>) : (
          <>
            <Kpi icon={DollarSign} label="Valor em estoque" value={brlCompact(data.total_value)} hint={brl(data.total_value)} tone="blue" />
            <Kpi icon={Boxes} label="Produtos cadastrados" value={num(data.total_items)} hint={`${num(data.total_units)} unidades no total`} tone="violet" />
            <Kpi icon={ShoppingCart} label="Saídas nos últimos 7 dias" value={`${num(data.sold_7d)} un.`}
              hint={delta === null ? "sem base de comparação" : (
                <span className={delta >= 0 ? "up" : "down"}>
                  {delta >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                  {Math.abs(delta).toFixed(0)}% vs. 7 dias anteriores
                </span>
              )} tone="orange" />
            <Kpi icon={TrendingDown} label="Precisam de reposição" value={num(data.low_stock.length)}
              hint={data.out_of_stock ? `${data.out_of_stock} esgotado(s)` : "nenhum esgotado"} tone={data.low_stock.length ? "red" : "green"} />
          </>
        )}
      </section>

      <section className="grid-main">
        <div className="card">
          <div className="card-title">
            <h2>Movimentações</h2><span className="muted">últimos 14 dias</span>
          </div>
          {data ? <MovementsChart data={data.daily} height={330} /> : <Skeleton height={260} />}
        </div>
        <div className="card">
          <div className="card-title">
            <h2><Layers size={16} /> Valor por categoria</h2>
          </div>
          {data ? <CategoryBars data={data.by_category} /> : <Skeleton height={220} />}
          <div className="divider" />
          <h3>Maiores valores em estoque</h3>
          <ul className="item-list tight">
            {data?.top_value.map((i) => (
              <li key={i.id} onClick={() => openItem(i.id)}>
                <ItemImage item={i} size="sm" />
                <div className="grow">
                  <b className="ellipsis">{i.name}</b>
                  <small className="muted">{i.quantity} un. × {brl(i.unit_price)}</small>
                </div>
                <b>{brlCompact(i.quantity * i.unit_price)}</b>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="grid-2">
        <div className="card">
          <div className="card-title">
            <h2>Itens críticos</h2>
            <button className="link-btn" onClick={() => onNavigate("produtos")}>Ver produtos →</button>
          </div>
          {data && data.low_stock.length === 0 && <p className="empty">Nenhum item abaixo do estoque mínimo. 🎉</p>}
          <ul className="item-list">
            {data?.low_stock.map((i) => (
              <li key={i.id} onClick={() => openItem(i.id)}>
                <ItemImage item={i} size="sm" />
                <div className="grow">
                  <div className="row-between">
                    <span><b>{i.name}</b> <span className="muted mono">{i.sku}</span></span>
                    <StockBadge item={i} />
                  </div>
                  <StockLevel item={i} />
                  <small className="muted">{i.quantity} em estoque · mínimo {i.min_quantity}</small>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="card-title">
            <h2>Últimas movimentações</h2>
            <button className="link-btn" onClick={() => onNavigate("movimentacoes")}>Ver todas →</button>
          </div>
          <ul className="activity">
            {data?.recent_movements.map((m) => (
              <li key={m.id} onClick={() => openItem(m.item_id)}>
                <span className={`mov-icon ${m.type}`}>{m.type === "entrada" ? "+" : "−"}</span>
                <div className="grow">
                  <b>{m.item}</b>
                  <small className="muted">{m.note || (m.type === "entrada" ? "Entrada" : "Saída")}</small>
                </div>
                <div className="right">
                  <b className={m.type}>{m.type === "entrada" ? "+" : "−"}{m.quantity}</b>
                  <small className="muted">{dateTime(m.created_at)}</small>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
