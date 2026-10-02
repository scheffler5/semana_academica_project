import { useEffect, useRef, useState } from "react";
import { Bot, ChevronDown, Loader2, MessageSquarePlus, Send, ShieldAlert, Sparkles, Wrench, X } from "lucide-react";
import { api, notifyChanged } from "../api.js";
import { useApp } from "../context.jsx";

const SUGGESTIONS = [
  "Quais itens estão com estoque baixo?",
  "Qual o valor total do estoque?",
  "Quantos mouses temos?",
  "Registre a venda de 2 headsets",
  "Em quantos dias o SSD vai acabar?",
  "Cadastre o produto Fone Bluetooth JBL, preço 199,90, 30 unidades, categoria Áudio",
];
const WRITE_TOOLS = new Set(["cadastrar_item", "atualizar_item", "registrar_movimentacao"]);
const BLOCK_LABELS = {
  sql_injection: "SQL injection",
  prompt_injection: "tentativa de alterar as instruções",
  secrets: "pedido de segredos/configuração",
  system_commands: "comando de sistema",
  infrastructure: "pedido sobre infraestrutura",
  too_long: "mensagem longa demais",
  control_chars: "caracteres inválidos",
};
const GREETING = {
  role: "bot",
  text: "Olá! Sou o assistente do estoque. Posso consultar quantidades e preços, cadastrar e alterar produtos, registrar entradas e saídas e prever quando um item vai acabar.",
};

function ToolTrace({ tools }) {
  if (!tools?.length) return null;
  return (
    <details className="trace">
      <summary><Wrench size={12} /> {tools.length} ferramenta(s): {tools.map((t) => t.function).join(" → ")}</summary>
      {tools.map((t, i) => (
        <div key={i} className="trace-step">
          <code>{t.function}({Object.entries(t.parameters).map(([k, v]) => `${k}="${v}"`).join(", ")})</code>
          {t.rationale && <div className="muted">💭 {t.rationale}</div>}
          {t.result && <pre>{t.result}</pre>}
        </div>
      ))}
    </details>
  );
}

export default function ChatWidget() {
  const { serviceStatus, health, refreshHealth } = useApp();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([GREETING]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [unread, setUnread] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading, open]);
  useEffect(() => { if (open) { setUnread(false); inputRef.current?.focus(); } }, [open]);

  const status = serviceStatus("agent");
  const mode = health?.agent_mode === "bedrock" ? "Amazon Bedrock" : "Agente simulado";

  const send = async (text) => {
    text = text.trim();
    if (!text || loading) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setLoading(true);
    try {
      const res = await api.chat(text, sessionId);
      setSessionId(res.session_id);
      setMessages((m) => [...m, { role: "bot", text: res.answer, tools: res.tools_used, blocked: res.blocked }]);
      if (res.tools_used.some((t) => WRITE_TOOLS.has(t.function))) notifyChanged(); // telas se atualizam
    } catch (err) {
      setMessages((m) => [...m, { role: "bot", error: true, text: err.message }]);
      if (err.service) refreshHealth();
    } finally {
      setLoading(false);
      if (!open) setUnread(true);
    }
  };

  return (
    <>
      <div className={`chat-panel ${open ? "open" : ""}`} aria-hidden={!open}>
        <header>
          <div className="chat-avatar"><Sparkles size={18} /></div>
          <div className="grow">
            <b>Assistente de estoque</b>
            <small><span className={`status-dot ${status === "down" ? "critical" : "good"}`} /> {status === "down" ? "indisponível" : mode}</small>
          </div>
          <button className="icon-btn light" title="Nova conversa" onClick={() => { setSessionId(null); setMessages([GREETING]); }}>
            <MessageSquarePlus size={18} />
          </button>
          <button className="icon-btn light" title="Minimizar" onClick={() => setOpen(false)}><ChevronDown size={20} /></button>
        </header>

        {status === "down" && (
          <div className="chat-alert">O assistente (Bedrock + Lambda) está fora do ar. As outras telas continuam funcionando.</div>
        )}

        <div className="chat-messages">
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role} ${m.error ? "error" : ""} ${m.blocked ? "blocked" : ""}`}>
              {m.role === "bot" && <Bot size={16} className="bubble-icon" />}
              <div>
                <div className="bubble-text">{m.text}</div>
                {m.blocked && (
                  <div className="blocked-tag"><ShieldAlert size={12} /> Bloqueado pelos guardrails: {BLOCK_LABELS[m.blocked] || m.blocked}</div>
                )}
                <ToolTrace tools={m.tools} />
              </div>
            </div>
          ))}
          {loading && (
            <div className="bubble bot typing">
              <Bot size={16} className="bubble-icon" />
              <div className="bubble-text"><Loader2 size={14} className="spin" /> consultando ferramentas…</div>
            </div>
          )}
          {messages.length === 1 && (
            <div className="chat-suggestions">
              {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(input); }}>
          <textarea
            ref={inputRef}
            rows={1}
            maxLength={500}
            value={input}
            placeholder="Pergunte sobre o estoque…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
          />
          <button className="send" disabled={loading || !input.trim()} aria-label="Enviar"><Send size={16} /></button>
        </form>
      </div>

      <button className={`chat-fab ${open ? "open" : ""}`} onClick={() => setOpen(!open)} aria-label="Assistente de IA">
        {open ? <X size={22} /> : <><Sparkles size={20} /><span>Assistente IA</span></>}
        {unread && !open && <span className="unread" />}
      </button>
    </>
  );
}
