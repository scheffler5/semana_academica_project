import { AlertTriangle, ArrowLeftRight, Boxes, Cloud, LayoutDashboard, PackagePlus, ServerCrash } from "lucide-react";
import { SERVICE_NAMES } from "../api.js";
import { useApp } from "../context.jsx";

export const NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "produtos", label: "Produtos", icon: Boxes },
  { id: "cadastro", label: "Cadastro", icon: PackagePlus },
  { id: "movimentacoes", label: "Movimentações", icon: ArrowLeftRight },
  { id: "arquitetura", label: "Arquitetura AWS", icon: Cloud },
];

const PILLS = ["s3", "agent"];
const SHORT = { s3: "S3", agent: "IA" };
const STATUS_TEXT = { ok: "operando", down: "fora do ar", disabled: "não configurado", simulated: "simulado", unknown: "verificando" };

export function Sidebar({ page, onNavigate }) {
  const { health } = useApp();
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo">📦</div>
        <div>
          <strong>Estoque Inteligente</strong>
          <small>Laboratório AWS</small>
        </div>
      </div>
      <nav>
        {NAV.map(({ id, label, icon: Icon }) => (
          <a key={id} href={`#/${id}`} className={page === id ? "active" : ""} onClick={() => onNavigate(id)}>
            <Icon size={18} /> <span>{label}</span>
          </a>
        ))}
      </nav>
      <div className="sidebar-footer">
        {health?.ec2 ? (
          <>
            <span className="env-dot aws" /> AWS · {health.ec2.availability_zone}
            <small>{health.ec2.instance_id} · {health.ec2.instance_type}</small>
          </>
        ) : (
          <>
            <span className="env-dot local" /> Ambiente local
            <small>emulando a arquitetura da AWS</small>
          </>
        )}
      </div>
    </aside>
  );
}

export function StatusPills() {
  const { serviceStatus, apiDown, health } = useApp();
  if (apiDown) {
    return <div className="pill down"><ServerCrash size={14} /> API fora do ar</div>;
  }
  return (
    <div className="pills">
      {PILLS.map((key) => {
        const status = serviceStatus(key);
        const info = health?.services?.[key];
        const tip = `${SERVICE_NAMES[key]}: ${STATUS_TEXT[status] || status}${info?.message ? ` — ${info.message}` : ""}${info?.latency_ms != null ? ` (${info.latency_ms} ms)` : ""}`;
        return (
          <span key={key} className={`pill ${status}`} title={tip}>
            <span className="dot" /> {SHORT[key]}
          </span>
        );
      })}
    </div>
  );
}

/** Faixa de aviso no topo quando algum serviço cai: diz o que é afetado e o que continua funcionando. */
export function ServiceBanner() {
  const { serviceStatus, apiDown, health } = useApp();
  const IMPACT = {
    s3: "Fotos e dados vivem no S3: nenhuma tela consegue ler ou gravar nada até ele voltar.",
    agent: "O assistente de IA não responde. O restante do sistema funciona normalmente.",
  };
  if (apiDown) {
    return (
      <div className="service-banner critical">
        <ServerCrash size={18} />
        <div><strong>{SERVICE_NAMES.api} fora do ar.</strong> O site continua carregado, mas nenhuma operação funciona. Tentando reconectar a cada 10 s…</div>
      </div>
    );
  }
  const down = Object.keys(IMPACT).filter((k) => serviceStatus(k) === "down");
  if (!down.length) return null;
  return (
    <div className="service-banner warning">
      <AlertTriangle size={18} />
      <div>
        {down.map((k) => (
          <div key={k}>
            <strong>{SERVICE_NAMES[k]} fora do ar.</strong> {IMPACT[k]}
          </div>
        ))}
      </div>
    </div>
  );
}
