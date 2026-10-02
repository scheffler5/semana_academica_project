// Camada de acesso à API. Todas as chamadas vão para /api no mesmo endereço do site
// (na EC2 o nginx repassa ao FastAPI). Nenhuma credencial existe no navegador.

export const SERVICE_NAMES = {
  api: "Servidor da aplicação (EC2)",
  s3: "Armazenamento (Amazon S3)",
  agent: "Assistente de IA (Bedrock + Lambda)",
};

export class ApiError extends Error {
  constructor(message, { status = 0, service = null, requestId = null, timeout = false } = {}) {
    super(message);
    this.timeout = timeout;
    this.status = status;
    this.service = service;
    this.requestId = requestId;
  }
}

async function request(method, path, body, { timeoutMs = 0 } = {}) {
  const options = { method, headers: {} };
  if (timeoutMs) options.signal = AbortSignal.timeout(timeoutMs);
  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(`/api${path}`, options);
  } catch (err) {
    if (err.name === "TimeoutError") {
      throw new ApiError("O servidor demorou demais para responder.", { service: "api", timeout: true });
    }
    throw new ApiError("Sem conexão com o servidor da aplicação (EC2). Verifique se a API está no ar.", {
      service: "api",
    });
  }
  if (res.status === 204) return null;

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    // 502/504 vêm do nginx (ou do proxy local) quando a API não responde
    if (!data || [502, 504].includes(res.status)) {
      throw new ApiError("O servidor da aplicação (EC2) não respondeu.", { status: res.status, service: "api" });
    }
    throw new ApiError(data.message || `Erro ${res.status}`, {
      status: res.status,
      service: data.service || null,
      requestId: data.request_id || null,
    });
  }
  return data;
}

export const api = {
  health: () => request("GET", "/health", undefined, { timeoutMs: 6000 }),
  dashboard: () => request("GET", "/dashboard"),
  categories: () => request("GET", "/categories"),
  listItems: ({ search = "", lowStock = false, category = "" } = {}) => {
    const q = new URLSearchParams({ search, low_stock: lowStock });
    if (category) q.set("category", category);
    return request("GET", `/items?${q}`);
  },
  getItem: (id) => request("GET", `/items/${id}`),
  previewSku: (category) => request("GET", `/items/next-sku?category=${encodeURIComponent(category || "Geral")}`),
  createItem: (item) => request("POST", "/items", item),
  updateItem: (id, item) => request("PUT", `/items/${id}`, item),
  deleteItem: (id) => request("DELETE", `/items/${id}`),
  uploadImage: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return request("POST", `/items/${id}/image`, form);
  },
  movements: (id) => request("GET", `/items/${id}/movements`),
  recentMovements: (limit = 50) => request("GET", `/movements?limit=${limit}`),
  addMovement: (id, movement) => request("POST", `/items/${id}/movements`, movement),
  forecast: (id) => request("GET", `/items/${id}/forecast`),
  chat: (message, sessionId) => request("POST", "/chat", { message, session_id: sessionId }),
};

// Avisa as telas que o estoque mudou (ex.: o assistente registrou uma venda)
export const notifyChanged = () => window.dispatchEvent(new Event("estoque:changed"));

export const brl = (v) => Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const brlCompact = (v) =>
  Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL", notation: "compact", maximumFractionDigits: 1 });

export const num = (v) => Number(v).toLocaleString("pt-BR");

const asDate = (iso) => new Date(iso.length === 10 ? `${iso}T12:00:00` : iso.endsWith("Z") ? iso : `${iso}Z`);

export const dateTime = (iso) =>
  asDate(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export const dayMonth = (iso) => asDate(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

export const weekday = (iso) => asDate(iso).toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
