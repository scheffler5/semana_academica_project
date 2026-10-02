import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

const HEALTH_INTERVAL_MS = 10000;

export function AppProvider({ children }) {
  // ---------- status dos serviços (atualizado a cada 10 s)
  const [health, setHealth] = useState(null);
  const [apiDown, setApiDown] = useState(false);
  const failures = useRef(0);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setApiDown(false);
      failures.current = 0;
    } catch (err) {
      // Conexão recusada = API fora do ar na hora. Lentidão isolada não: exige 2 timeouts seguidos
      failures.current += 1;
      if (!err.timeout || failures.current >= 2) setApiDown(true);
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    const timer = setInterval(refreshHealth, HEALTH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refreshHealth]);

  const serviceStatus = (key) => {
    if (apiDown) return "down";
    return health?.services?.[key]?.status ?? "unknown";
  };

  // ---------- notificações (toasts)
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(1);
  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const toast = useCallback((type, title, message) => {
    const id = nextId.current++;
    setToasts((t) => [...t.slice(-3), { id, type, title, message }]);
    setTimeout(() => dismiss(id), type === "error" ? 9000 : 4500);
  }, [dismiss]);

  // Erro de API -> toast; se for falha de serviço, atualiza a barra de status na hora
  const toastError = useCallback((err, title = "Não foi possível concluir") => {
    toast("error", title, err.message + (err.requestId ? ` (código ${err.requestId})` : ""));
    if (err.service) refreshHealth();
  }, [toast, refreshHealth]);

  // ---------- item aberto no painel lateral
  const [openItemId, setOpenItemId] = useState(null);

  return (
    <AppContext.Provider value={{
      health, apiDown, refreshHealth, serviceStatus,
      toasts, toast, toastError, dismiss,
      openItemId, openItem: setOpenItemId, closeItem: () => setOpenItemId(null),
    }}>
      {children}
    </AppContext.Provider>
  );
}

// Recarrega dados quando o estoque muda em qualquer lugar (inclusive pelo assistente)
export function useOnStockChange(callback) {
  const ref = useRef(callback);
  ref.current = callback;
  useEffect(() => {
    const handler = () => ref.current();
    window.addEventListener("estoque:changed", handler);
    return () => window.removeEventListener("estoque:changed", handler);
  }, []);
}
