import { Activity, Bot, Download, HardDrive, KeyRound, Network, RefreshCw, Server, Zap } from "lucide-react";
import ArchitectureDiagram from "../components/ArchitectureDiagram.jsx";
import { PageHeader } from "../components/ui.jsx";
import { useApp } from "../context.jsx";

const STATUS = {
  ok: ["good", "Operando"],
  simulated: ["neutral", "Simulado (local)"],
  disabled: ["neutral", "Não configurado"],
  down: ["critical", "Fora do ar"],
  unknown: ["neutral", "Verificando…"],
  static: ["neutral", "Infraestrutura"],
};

const CARDS = [
  { key: "api", icon: Server, name: "Amazon EC2", local: "uvicorn na sua máquina",
    role: "Servidor na sub-rede pública: o nginx entrega o site (React) e repassa /api para o FastAPI." },
  { key: "s3", icon: HardDrive, name: "Amazon S3", local: "emulador Moto (API do S3)",
    role: "Bucket privado com as fotos E os dados do estoque (items.json/movements.json): é o único armazenamento do sistema. O navegador nunca acessa o S3 direto; tudo passa pela API." },
  { key: "agent", icon: Bot, name: "Amazon Bedrock Agents", local: "agente simulado (regras)",
    role: "LLM (Claude) com Guardrails: entende o pedido e decide qual ferramenta usar." },
  { key: "agent", icon: Zap, name: "AWS Lambda", local: "mesmo código, executado localmente",
    role: "Ferramentas do agente com validação e permissões; chama a API pelo IP privado da VPC." },
  { key: null, icon: Network, name: "Amazon VPC + Internet Gateway", local: "localhost",
    role: "Rede isolada em 2 zonas de disponibilidade: sub-rede pública (EC2, acessível pela internet) e privada (Lambda, só alcançável de dentro da VPC)." },
  { key: null, icon: KeyRound, name: "AWS IAM", local: "credenciais falsas só para o emulador",
    role: "Roles para EC2, Lambda e Agent com privilégio mínimo: nada de chaves de acesso no código." },
  { key: null, icon: Activity, name: "Amazon CloudWatch", local: "logs no terminal",
    role: "Logs da API e da Lambda; o código de erro (request_id) mostrado na tela é buscado aqui." },
];

export default function Arquitetura() {
  const { health, apiDown, serviceStatus, refreshHealth } = useApp();
  const local = health?.environment !== "aws";
  const s = (k) => (apiDown ? "down" : k === "api" ? "ok" : serviceStatus(k));

  const exportPng = () => {
    // Converte o SVG do diagrama em PNG (2x) para usar em slides
    const svg = document.querySelector(".arch-diagram");
    const clone = svg.cloneNode(true);
    const styles = getComputedStyle(document.documentElement);
    // O PNG não enxerga o CSS da página: copiamos o estilo calculado de cada texto
    const originals = svg.querySelectorAll("text");
    clone.querySelectorAll("text").forEach((t, i) => {
      const cs = getComputedStyle(originals[i]);
      ["font-family", "font-size", "font-weight", "font-style", "fill", "stroke", "stroke-width", "paint-order"]
        .forEach((prop) => t.style.setProperty(prop, cs.getPropertyValue(prop)));
    });
    clone.setAttribute("width", 2400);
    clone.setAttribute("height", 1540);
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" }));
    const img = new Image();
    img.onload = () => {
      const canvas = Object.assign(document.createElement("canvas"), { width: 2400, height: 1540 });
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = styles.getPropertyValue("--surface") || "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      Object.assign(document.createElement("a"), { href: canvas.toDataURL("image/png"), download: "arquitetura-aws.png" }).click();
    };
    img.src = url;
  };

  return (
    <>
      <PageHeader
        title="Arquitetura AWS"
        subtitle={local ? "Arquitetura final na AWS · status ao vivo do ambiente local" : `Rodando na AWS · ${health?.region}`}
        actions={<>
          <button className="btn" onClick={exportPng}><Download size={16} /> Baixar PNG</button>
          <button className="btn" onClick={refreshHealth}><RefreshCw size={16} /> Atualizar status</button>
        </>}
      />

      <div className="card">
        <ArchitectureDiagram status={{ api: s("api"), s3: s("s3"), agent: s("agent") }} />
      </div>

      <div className="service-cards">
        {CARDS.map(({ key, icon: Icon, name, role, local: localName }) => {
          const status = key ? s(key) : "static";
          const [tone, label] = STATUS[status] || STATUS.unknown;
          const info = key ? health?.services?.[key] : null;
          return (
            <article key={name} className="card service-card">
              <header>
                <div className="kpi-icon blue"><Icon size={18} /></div>
                <h3>{name}</h3>
                <span className={`badge ${tone}`}>{label}</span>
              </header>
              <p>{role}</p>
              <small className="muted">
                {local && <>Local: {localName}. </>}
                {info?.message && <>{info.message}. </>}
                {info?.latency_ms != null && <>Latência {info.latency_ms} ms.</>}
                {key === "api" && health?.ec2 && <>{health.ec2.instance_id} · {health.ec2.instance_type} · {health.ec2.availability_zone}</>}
              </small>
            </article>
          );
        })}
      </div>
    </>
  );
}
