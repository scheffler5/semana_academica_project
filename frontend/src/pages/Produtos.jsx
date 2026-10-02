import { useCallback, useEffect, useState } from "react";
import { LayoutGrid, List, PackagePlus, Search } from "lucide-react";
import { api, brl } from "../api.js";
import { ErrorState, ItemImage, PageHeader, Skeleton, StockBadge, StockLevel } from "../components/ui.jsx";
import { useApp, useOnStockChange } from "../context.jsx";

export default function Produtos({ onNavigate }) {
  const { openItem } = useApp();
  const [items, setItems] = useState(null);
  const [categories, setCategories] = useState([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [view, setView] = useState("grid");
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api.listItems({ search, lowStock: lowOnly, category })
      .then((list) => { setItems(list); setError(null); })
      .catch(setError);
  }, [search, lowOnly, category]);

  useEffect(() => {
    const t = setTimeout(load, 250); // espera parar de digitar
    return () => clearTimeout(t);
  }, [load]);
  useEffect(() => { api.categories().then(setCategories).catch(() => {}); }, []);
  useOnStockChange(load);

  return (
    <>
      <PageHeader
        title="Produtos"
        subtitle={items ? `${items.length} produto(s)` : "Carregando catálogo…"}
        actions={<button className="btn primary" onClick={() => onNavigate("cadastro")}><PackagePlus size={16} /> Novo produto</button>}
      />

      <div className="toolbar card">
        <label className="search">
          <Search size={16} />
          <input placeholder="Buscar por nome, SKU ou categoria…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Todas as categorias</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <label className="switch">
          <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} />
          <span /> Só estoque baixo
        </label>
        <div className="segmented">
          <button className={view === "grid" ? "on" : ""} onClick={() => setView("grid")} aria-label="Grade"><LayoutGrid size={16} /></button>
          <button className={view === "list" ? "on" : ""} onClick={() => setView("list")} aria-label="Lista"><List size={16} /></button>
        </div>
      </div>

      {error && <ErrorState error={error} onRetry={load} />}

      {!items && !error && (
        <div className="product-grid">{[1, 2, 3, 4, 5, 6, 7, 8].map((i) => <div key={i} className="card"><Skeleton height={220} /></div>)}</div>
      )}

      {items && items.length === 0 && <div className="card empty">Nenhum produto encontrado.</div>}

      {items && view === "grid" && (
        <div className="product-grid">
          {items.map((i) => (
            <article key={i.id} className="card product" onClick={() => openItem(i.id)}>
              <ItemImage item={i} size="lg" />
              <div className="product-body">
                <div className="row-between">
                  <span className="chip">{i.category}</span>
                  <span className="muted mono">{i.sku}</span>
                </div>
                <h3>{i.name}</h3>
                <div className="row-between">
                  <span className="price">{brl(i.unit_price)}</span>
                  <StockBadge item={i} />
                </div>
                <StockLevel item={i} />
                <small className="muted">{i.quantity} un. em estoque · mín. {i.min_quantity}</small>
              </div>
            </article>
          ))}
        </div>
      )}

      {items && view === "list" && items.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr><th></th><th>Produto</th><th>Categoria</th><th className="num">Preço</th><th className="num">Estoque</th><th>Situação</th></tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id} onClick={() => openItem(i.id)} className="clickable">
                  <td><ItemImage item={i} size="sm" /></td>
                  <td><b>{i.name}</b><br /><span className="muted mono">{i.sku}</span></td>
                  <td>{i.category}</td>
                  <td className="num">{brl(i.unit_price)}</td>
                  <td className="num">{i.quantity} <span className="muted">/ mín. {i.min_quantity}</span></td>
                  <td><StockBadge item={i} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
