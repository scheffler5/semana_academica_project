import { Minus, Plus } from "lucide-react";

const fmt = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MAX_CENTS = 10_000_000_00; // R$ 10 milhões

/**
 * Campo de dinheiro com máscara: o usuário digita só números e o valor é preenchido
 * a partir dos centavos (1 → 0,01 · 19990 → 199,90 · 129990 → 1.299,90).
 * `value` e `onChange` trabalham com número em reais (ex.: 1299.9).
 */
export function CurrencyInput({ value, onChange, id, required, placeholder = "0,00", autoFocus }) {
  const cents = Math.round((Number(value) || 0) * 100);

  const handleChange = (e) => {
    const digits = e.target.value.replace(/\D/g, "").replace(/^0+/, "");
    const next = Math.min(Number(digits || 0), MAX_CENTS);
    onChange(next / 100);
  };

  return (
    <div className="currency-input">
      <span className="prefix">R$</span>
      <input
        id={id}
        inputMode="numeric"
        autoComplete="off"
        required={required}
        autoFocus={autoFocus}
        placeholder={placeholder}
        value={cents ? fmt.format(cents / 100) : ""}
        onChange={handleChange}
        onFocus={(e) => e.target.select()}
      />
    </div>
  );
}

/** Campo numérico inteiro com botões − e +. */
export function NumberStepper({ value, onChange, min = 0, max = 100000, id }) {
  const n = Number(value) || 0;
  const set = (v) => onChange(Math.max(min, Math.min(max, v)));
  return (
    <div className="stepper">
      <button type="button" onClick={() => set(n - 1)} disabled={n <= min} aria-label="Diminuir"><Minus size={14} /></button>
      <input
        id={id}
        inputMode="numeric"
        value={n}
        onChange={(e) => set(Number(e.target.value.replace(/\D/g, "")) || 0)}
        onFocus={(e) => e.target.select()}
      />
      <button type="button" onClick={() => set(n + 1)} disabled={n >= max} aria-label="Aumentar"><Plus size={14} /></button>
    </div>
  );
}
