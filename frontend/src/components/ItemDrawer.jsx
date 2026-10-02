import { useEffect, useRef, useState } from "react";
import { Camera, Loader2, Minus, Pencil, Plus, Sparkles, Trash2, X } from "lucide-react";
import { api, brl, dateTime, notifyChanged } from "../api.js";
import { HistoryBars } from "../charts/charts.jsx";
import { CurrencyInput, NumberStepper } from "./inputs.jsx";
import { useApp, useOnStockChange } from "../context.jsx";
import { ErrorState, ItemImage, Skeleton, StockBadge, StockLevel } from "./ui.jsx";

export default function ItemDrawer() {
  const { openItemId, closeItem, toast, toastError } = useApp();
  const [item, setItem] = useState(null);
  const [movements, setMovements] = useState([]);
  const [error, setError] = useState(null);
  const [move, setMove] = useState({ type: "saida", quantity: 1, note: "" });
  const [editing, setEditing] = useState(false);
  const [edit, setEdit] = useState({});
  const [forecast, setForecast] = useState(null);
  const [busy, setBusy] = useState("");
  const fileRef = useRef(null);

  const load = async (id = openItemId) => {
    if (!id) return;
    try {
      const [it, mv] = await Promise.all([api.getItem(id), api.movements(id)]);
      setItem(it);
      setMovements(mv);
      setError(null);
    } catch (err) {
      setError(err);
    }
  };

  useEffect(() => {
    setItem(null);
    setForecast(null);
    setEditing(false);
    setError(null);
    load();
  }, [openItemId]); // eslint-disable-line react-hooks/exhaustive-deps
  useOnStockChange(() => load());

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && closeItem();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeItem]);

  if (!openItemId) return null;

  const run = async (label, fn, successTitle) => {
    setBusy(label);
    try {
      await fn();
      if (successTitle) toast("success", successTitle);
    } catch (err) {
      toastError(err);
    } finally {
      setBusy("");
    }
  };

  const submitMove = (e) => {
    e.preventDefault();
    run("move", async () => {
      await api.addMovement(item.id, { ...move, quantity: Number(move.quantity) });
      setMove({ ...move, quantity: 1, note: "" });
      setForecast(null);
      notifyChanged();
    }, move.type === "entrada" ? "Entrada registrada" : "Saída registrada");
  };

  const saveEdit = (e) => {
    e.preventDefault();
    run("edit", async () => {
      await api.updateItem(item.id, {
        name: edit.name,
        category: edit.category,
        unit_price: edit.unit_price,
        min_quantity: edit.min_quantity,
      });
      setEditing(false);
      notifyChanged();
    }, "Produto atualizado");
  };

  const uploadPhoto = (file) => file && run("photo", async () => {
    await api.uploadImage(item.id, file);
    notifyChanged();
  }, "Foto enviada ao S3");

  const remove = () => {
    if (!confirm(`Excluir "${item.name}" e todo o histórico?`)) return;
    run("delete", async () => {
      await api.deleteItem(item.id);
      closeItem();
      notifyChanged();
    }, "Produto excluído");
  };

  const runForecast = () => run("forecast", async () => setForecast(await api.forecast(item.id)));

  return (
    <div className="drawer-bg" onClick={closeItem}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Detalhes do produto">
        <header className="drawer-head">
          <div>
            <span className="muted mono">{item?.sku}</span>
            <h2>{item?.name || "Carregando…"}</h2>
          </div>
          <button className="icon-btn" onClick={closeItem} aria-label="Fechar"><X size={18} /></button>
        </header>

        {error && <ErrorState error={error} onRetry={() => load()} compact />}
        {!item && !error && <div className="drawer-body"><Skeleton height={200} /><Skeleton height={120} style={{ marginTop: 16 }} /></div>}

        {item && (
          <div className="drawer-body">
            <div className="drawer-photo">
              <ItemImage item={item} size="xl" />
              <button className="btn photo-btn" onClick={() => fileRef.current.click()} disabled={busy === "photo"}>
                {busy === "photo" ? <Loader2 size={16} className="spin" /> : <Camera size={16} />}
                {item.image_url ? "Trocar foto" : "Enviar foto"}
              </button>
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => uploadPhoto(e.target.files[0])} />
            </div>

            {!editing ? (
              <div className="facts">
                <div><span>Preço</span><b>{brl(item.unit_price)}</b></div>
                <div><span>Em estoque</span><b>{item.quantity} un.</b></div>
                <div><span>Mínimo</span><b>{item.min_quantity} un.</b></div>
                <div><span>Valor total</span><b>{brl(item.quantity * item.unit_price)}</b></div>
                <div className="span-2">
                  <div className="row-between"><span className="chip">{item.category}</span><StockBadge item={item} /></div>
                  <StockLevel item={item} />
                </div>
                <button className="link-btn" onClick={() => { setEdit(item); setEditing(true); }}><Pencil size={14} /> Editar dados</button>
              </div>
            ) : (
              <form className="form-grid edit-form" onSubmit={saveEdit}>
                <label className="full">Nome<input required value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></label>
                <label>Categoria<input value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })} /></label>
                <label>Preço<CurrencyInput value={edit.unit_price} onChange={(v) => setEdit({ ...edit, unit_price: v })} required /></label>
                <label>Estoque mínimo<NumberStepper value={edit.min_quantity} onChange={(v) => setEdit({ ...edit, min_quantity: v })} /></label>
                <div className="form-actions">
                  <button type="button" className="btn" onClick={() => setEditing(false)}>Cancelar</button>
                  <button className="btn primary" disabled={busy === "edit"}>Salvar</button>
                </div>
              </form>
            )}

            <section>
              <h3>Registrar movimentação</h3>
              <form className="move-form" onSubmit={submitMove}>
                <div className="segmented text">
                  <button type="button" className={move.type === "saida" ? "on" : ""} onClick={() => setMove({ ...move, type: "saida" })}><Minus size={14} /> Saída</button>
                  <button type="button" className={move.type === "entrada" ? "on" : ""} onClick={() => setMove({ ...move, type: "entrada" })}><Plus size={14} /> Entrada</button>
                </div>
                <NumberStepper value={move.quantity} onChange={(v) => setMove({ ...move, quantity: v })} min={1} />
                <input placeholder="Observação (opcional)" value={move.note} onChange={(e) => setMove({ ...move, note: e.target.value })} />
                <button className="btn primary" disabled={busy === "move"}>Registrar</button>
              </form>
            </section>

            <section>
              <h3>Previsão de demanda</h3>
              {!forecast ? (
                <button className="btn ai" onClick={runForecast} disabled={busy === "forecast"}>
                  {busy === "forecast" ? <><Loader2 size={16} className="spin" /> Calculando…</> : <><Sparkles size={16} /> Calcular previsão</>}
                </button>
              ) : (
                <div className="forecast">
                  <small className="muted">Saídas por dia nos últimos 14 dias</small>
                  <HistoryBars values={forecast.history_14_days} />
                  <div className="forecast-numbers">
                    <div><span>Próximos 7 dias</span><b>{forecast.predicted_next_7_days} un.</b></div>
                    <div><span>Por dia</span><b>~{forecast.predicted_daily}</b></div>
                    <div><span>Acaba em</span><b>{forecast.days_until_out != null ? `${forecast.days_until_out} dias` : "—"}</b></div>
                  </div>
                  <p className="recommendation">{forecast.recommendation}</p>
                  <small className="muted">Média móvel das saídas dos últimos 7 dias</small>
                </div>
              )}
            </section>

            <section>
              <h3>Histórico</h3>
              <ul className="activity compact">
                {movements.slice(0, 15).map((m) => (
                  <li key={m.id}>
                    <span className={`mov-icon ${m.type}`}>{m.type === "entrada" ? "+" : "−"}</span>
                    <div className="grow"><span>{m.note || (m.type === "entrada" ? "Entrada" : "Saída")}</span></div>
                    <div className="right">
                      <b className={m.type}>{m.type === "entrada" ? "+" : "−"}{m.quantity}</b>
                      <small className="muted">{dateTime(m.created_at)}</small>
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            <button className="btn danger" onClick={remove} disabled={busy === "delete"}><Trash2 size={16} /> Excluir produto</button>
          </div>
        )}
      </aside>
    </div>
  );
}
