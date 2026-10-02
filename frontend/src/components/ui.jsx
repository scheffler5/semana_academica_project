import { useState } from "react";
import {
  AlertTriangle, CheckCircle2, CircleSlash, ImageOff, Info, Package, RefreshCw, Server, Sparkles, X,
} from "lucide-react";
import { SERVICE_NAMES } from "../api.js";
import { useApp } from "../context.jsx";

const SERVICE_ICONS = { api: Server, s3: ImageOff, agent: Sparkles };

/** Estado de erro de uma tela inteira, dizendo qual serviço falhou. */
export function ErrorState({ error, onRetry, compact = false }) {
  const Icon = SERVICE_ICONS[error?.service] || AlertTriangle;
  const service = error?.service ? SERVICE_NAMES[error.service] : null;
  return (
    <div className={`error-state ${compact ? "compact" : ""}`} role="alert">
      <div className="error-icon"><Icon size={compact ? 20 : 28} /></div>
      <div>
        <strong>{service ? `${service} indisponível` : "Algo deu errado"}</strong>
        <p>{error?.message}</p>
        {error?.requestId && <small className="muted">Código do erro: {error.requestId}</small>}
      </div>
      {onRetry && (
        <button className="btn" onClick={onRetry}><RefreshCw size={16} /> Tentar de novo</button>
      )}
    </div>
  );
}

/** Foto do item, com placeholder quando não há foto OU quando o S3 está fora do ar. */
export function ItemImage({ item, size = "md" }) {
  const [failed, setFailed] = useState(false);
  const { serviceStatus } = useApp();
  if (!item.image_url || failed) {
    const s3Down = item.image_url && (failed || serviceStatus("s3") === "down");
    return (
      <div className={`thumb thumb-${size} placeholder`} title={s3Down ? "Foto indisponível: S3 fora do ar" : "Sem foto"}>
        {s3Down ? <ImageOff size={size === "sm" ? 16 : 28} /> : <Package size={size === "sm" ? 16 : 28} />}
        {size !== "sm" && <span>{s3Down ? "Foto indisponível" : "Sem foto"}</span>}
      </div>
    );
  }
  return (
    <div className={`thumb thumb-${size}`}>
      <img src={item.image_url} alt={item.name} loading="lazy" onError={() => setFailed(true)} />
    </div>
  );
}

/** Situação do estoque com cor de status + ícone + texto (nunca só cor). */
export function StockBadge({ item }) {
  if (item.quantity === 0) return <span className="badge critical"><CircleSlash size={12} /> Esgotado</span>;
  if (item.low_stock) return <span className="badge warning"><AlertTriangle size={12} /> Estoque baixo</span>;
  return <span className="badge good"><CheckCircle2 size={12} /> Normal</span>;
}

/** Barra de nível: quantidade em relação a 3x o estoque mínimo. */
export function StockLevel({ item }) {
  const target = Math.max(item.min_quantity * 3, 1);
  const pct = Math.min(100, (item.quantity / target) * 100);
  const minPct = Math.min(100, (item.min_quantity / target) * 100);
  const level = item.quantity === 0 ? "critical" : item.low_stock ? "warning" : "good";
  return (
    <div className="stock-level" title={`${item.quantity} un. · mínimo ${item.min_quantity}`}>
      <div className={`fill ${level}`} style={{ width: `${pct}%` }} />
      <div className="min-mark" style={{ left: `${minPct}%` }} />
    </div>
  );
}

export function Toasts() {
  const { toasts, dismiss } = useApp();
  const icons = { success: CheckCircle2, error: AlertTriangle, info: Info, warning: AlertTriangle };
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => {
        const Icon = icons[t.type] || Info;
        return (
          <div key={t.id} className={`toast ${t.type}`}>
            <Icon size={18} />
            <div>
              <strong>{t.title}</strong>
              {t.message && <p>{t.message}</p>}
            </div>
            <button className="icon-btn" onClick={() => dismiss(t.id)} aria-label="Fechar"><X size={14} /></button>
          </div>
        );
      })}
    </div>
  );
}

export function Skeleton({ height = 16, width = "100%", style }) {
  return <div className="skeleton" style={{ height, width, ...style }} />;
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
