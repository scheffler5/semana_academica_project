import { useCallback, useEffect, useState } from "react";
import { api, dateTime } from "../api.js";
import { ErrorState, PageHeader, Skeleton } from "../components/ui.jsx";
import { useApp, useOnStockChange } from "../context.jsx";

export default function Movimentacoes() {
  const { openItem } = useApp();
  const [rows, setRows] = useState(null);
  const [type, setType] = useState("");
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api.recentMovements(100).then((r) => { setRows(r); setError(null); }).catch(setError);
  }, []);
  useEffect(load, [load]);
  useOnStockChange(load);

  const visible = rows?.filter((r) => !type || r.type === type);

  return (
    <>
      <PageHeader title="Movimentações" subtitle="Entradas e saídas mais recentes (inclusive as registradas pelo assistente)"
        actions={
          <div className="segmented text">
            {[["", "Todas"], ["entrada", "Entradas"], ["saida", "Saídas"]].map(([v, label]) => (
              <button key={v} className={type === v ? "on" : ""} onClick={() => setType(v)}>{label}</button>
            ))}
          </div>
        } />
      {error && <ErrorState error={error} onRetry={load} />}
      {!rows && !error && <div className="card"><Skeleton height={300} /></div>}
      {visible && (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>Data</th><th>Produto</th><th>Tipo</th><th className="num">Qtd.</th><th>Observação</th></tr></thead>
            <tbody>
              {visible.map((m) => (
                <tr key={m.id} className="clickable" onClick={() => openItem(m.item_id)}>
                  <td className="muted">{dateTime(m.created_at)}</td>
                  <td><b>{m.item}</b> <span className="muted mono">{m.sku}</span></td>
                  <td><span className={`badge ${m.type === "entrada" ? "in" : "out"}`}>{m.type === "entrada" ? "Entrada" : "Saída"}</span></td>
                  <td className={`num ${m.type}`}><b>{m.type === "entrada" ? "+" : "−"}{m.quantity}</b></td>
                  <td className="muted">{m.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
