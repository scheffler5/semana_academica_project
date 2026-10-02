import { Activity, Bot, Cloud, Globe, HardDrive, KeyRound, Network, Server, Users, Zap } from "lucide-react";

// Cores das categorias de serviço usadas nos diagramas oficiais da AWS
const C = {
  compute: "#ED7100",
  storage: "#7AA116",
  ai: "#01A88D",
  management: "#E7157B",
  security: "#DD344C",
  network: "#8C4FFF",
  dark: "#232F3E",
};
const STATUS_COLOR = { ok: "#0ca30c", simulated: "#2a78d6", down: "#d03b3b", disabled: "#94a3b8", unknown: "#94a3b8" };

/** Ícone de serviço no estilo AWS: quadrado colorido + símbolo branco + rótulo embaixo. */
function Service({ x, y, icon: Icon, color, title, subtitle, status, dashed = false, size = 56 }) {
  const h = size / 2;
  return (
    <g transform={`translate(${x},${y})`} className={dashed ? "svc dashed" : "svc"}>
      <rect x={-h} y={-h} width={size} height={size} rx={8} fill={dashed ? "#fff" : color}
        stroke={color} strokeWidth={dashed ? 1.5 : 0} strokeDasharray={dashed ? "4 3" : undefined} />
      <Icon x={-h + size * 0.2} y={-h + size * 0.2} width={size * 0.6} height={size * 0.6}
        color={dashed ? color : "#fff"} strokeWidth={1.8} />
      {status && <circle cx={h - 2} cy={-h + 2} r={7} fill={STATUS_COLOR[status] || STATUS_COLOR.unknown} stroke="#fff" strokeWidth={2.5} />}
      <text y={h + 17} textAnchor="middle" className="d-title">{title}</text>
      {subtitle && <text y={h + 32} textAnchor="middle" className="d-sub">{subtitle}</text>}
    </g>
  );
}

/** Agrupamento (AWS Cloud, Região, VPC, AZ, sub-rede) com rótulo no canto. */
function Group({ x, y, w, h, label, stroke, fill = "none", dashed = false, icon: Icon, labelColor }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={4} fill={fill} stroke={stroke} strokeWidth={1.5}
        strokeDasharray={dashed ? "6 4" : undefined} />
      {Icon && <rect x={x} y={y} width={26} height={26} fill={stroke} />}
      {Icon && <Icon x={x + 5} y={y + 5} width={16} height={16} color="#fff" strokeWidth={2} />}
      <text x={x + (Icon ? 34 : 10)} y={y + 18} className="d-group" fill={labelColor || stroke}>{label}</text>
    </g>
  );
}

/** Fluxo numerado: linha com seta + círculo com o número + rótulo. */
function Flow({ points, n, label, lx, ly, anchor = "middle", dashed = false, below = false }) {
  return (
    <g className="flow">
      <polyline points={points} fill="none" stroke={C.dark} strokeWidth={1.6}
        strokeDasharray={dashed ? "5 4" : undefined} markerEnd="url(#arrow)" />
      {n && (
        <g transform={`translate(${lx},${ly})`}>
          <circle r={9} fill={C.dark} />
          <text y={4} textAnchor="middle" className="d-num">{n}</text>
          <text x={anchor === "start" ? 14 : anchor === "end" ? -14 : 0} y={anchor === "middle" ? (below ? 24 : -14) : 4}
            textAnchor={anchor} className="d-flow">{label}</text>
        </g>
      )}
    </g>
  );
}

export default function ArchitectureDiagram({ status = {} }) {
  return (
    <figure className="arch-figure">
      <svg viewBox="0 0 1200 720" className="arch-diagram" role="img"
        aria-label="Arquitetura do Estoque Inteligente na AWS: usuários acessam a EC2 pública via Internet Gateway; a EC2 grava os dados e as fotos no S3 e consulta o Bedrock Agent, que aciona a Lambda na sub-rede privada; a Lambda chama a API da EC2 pelo IP privado.">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill={C.dark} />
          </marker>
        </defs>

        {/* -------- agrupamentos */}
        <Group x={190} y={14} w={990} h={680} label="AWS Cloud" stroke={C.dark} icon={Cloud} />
        <Group x={210} y={54} w={950} h={624} label="Região us-east-1 (N. Virginia)" stroke="#00A4A6" dashed />
        <Group x={240} y={96} w={570} h={534} label="VPC 10.0.0.0/16" stroke={C.network} icon={Network} />

        <Group x={290} y={152} w={500} h={240} label="AZ us-east-1a" stroke="#147EBA" dashed />
        <Group x={306} y={184} w={214} h={192} label="Sub-rede pública" stroke={C.storage} fill="#F2F6E8" labelColor="#3d5c0a" />
        <Group x={556} y={184} w={218} h={192} label="Sub-rede privada" stroke="#00A4A6" fill="#E6F6F7" labelColor="#006b6d" />

        <Group x={290} y={410} w={500} h={204} label="AZ us-east-1b" stroke="#147EBA" dashed />
        <Group x={306} y={442} w={214} h={156} label="Sub-rede pública" stroke={C.storage} fill="#F2F6E8" labelColor="#3d5c0a" />
        <Group x={556} y={442} w={218} h={156} label="Sub-rede privada" stroke="#00A4A6" fill="#E6F6F7" labelColor="#006b6d" />

        {/* -------- fluxos (desenhados antes dos ícones para passar por baixo) */}
        <Flow points="105,280 222,280" />
        <Flow points="270,280 420,280" n="1" label="HTTP :80" lx={150} ly={280} />
        <Flow points="636,280 478,280" n="5" label="HTTP /api · IP privado" lx={558} ly={280} below />
        <Flow points="440,250 440,124 918,124 918,170 960,170" n="2" label="dados e fotos (IAM Role)" lx={680} ly={124} />
        <Flow points="464,250 464,140 902,140 902,330 960,330" n="3" label="InvokeAgent" lx={902} ly={258} anchor="start" />
        <Flow points="960,340 760,340 760,280 686,280" n="4" label="executa ferramenta" lx={850} ly={340} />
        <Flow points="686,264 872,264 872,498 960,498" dashed n="6" label="logs" lx={872} ly={420} anchor="start" />

        {/* -------- serviços */}
        <Service x={75} y={280} icon={Users} color={C.dark} title="Usuários" subtitle="PCs do laboratório" />
        <Service x={246} y={280} icon={Globe} color={C.network} title="Internet" subtitle="Gateway" size={44} />

        <Service x={450} y={280} icon={Server} color={C.compute} title="Amazon EC2" subtitle="nginx · React · FastAPI" status={status.api} />
        <text x={450} y={358} textAnchor="middle" className="d-tag">SG :80 · IAM Role</text>

        <Service x={660} y={280} icon={Zap} color={C.compute} title="AWS Lambda" subtitle="ferramentas do agente" status={status.agent} size={48} />

        <text x={412} y={508} textAnchor="middle" className="d-muted">reservada para</text>
        <text x={412} y={524} textAnchor="middle" className="d-muted">alta disponibilidade</text>
        <Service x={660} y={520} icon={Zap} color={C.compute} title="Lambda (ENI)" dashed size={34} />

        <text x={862} y={92} className="d-group" fill="#006b6d">Serviços regionais (fora da VPC)</text>
        <Service x={990} y={170} icon={HardDrive} color={C.storage} title="Amazon S3" subtitle="bucket privado · dados e fotos" status={status.s3} />
        <Service x={990} y={340} icon={Bot} color={C.ai} title="Amazon Bedrock" subtitle="Agent + Claude + Guardrails" status={status.agent} />
        <Service x={990} y={498} icon={Activity} color={C.management} title="CloudWatch" subtitle="logs e métricas" />
        <Service x={990} y={598} icon={KeyRound} color={C.security} title="IAM" subtitle="roles EC2 · Lambda · Agent" />
      </svg>
      <figcaption>
        <b>1</b> Os usuários acessam a EC2 pela internet (Internet Gateway, porta 80). <b>2</b> A API lê e grava os dados
        (JSON) e as fotos no mesmo bucket S3 privado, com as credenciais temporárias da IAM Role — é o único armazenamento
        do sistema. <b>3</b> O chat é enviado ao Bedrock Agent, que <b>4</b> executa as ferramentas na Lambda, na sub-rede
        privada; a Lambda <b>5</b> chama a API pelo IP privado, sem sair da VPC. <b>6</b> Tudo registra logs no CloudWatch.
        Nenhuma chave de acesso existe no código.
      </figcaption>
    </figure>
  );
}
