import { useEffect, useRef, useState } from "react";
import { brl, brlCompact, dayMonth, num, weekday } from "../api.js";

// Paleta validada (contraste + daltonismo): série 1 azul, série 2 laranja
export const SERIES = { entradas: "#2a78d6", saidas: "#eb6834" };

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    if (!ref.current) return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

// Coluna com só o topo arredondado (a base fica reta, ancorada no eixo)
function columnPath(x, y, w, h, r = 4) {
  if (h <= 0) return "";
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h} V${y + rr} Q${x},${y} ${x + rr},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h} Z`;
}

function niceMax(value) {
  if (value <= 0) return 4;
  const pow = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * pow * 4 >= value) * pow;
  return step * 4;
}

/** Entradas x saídas por dia (colunas agrupadas, um eixo só). */
export function MovementsChart({ data, height = 260 }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const [asTable, setAsTable] = useState(false);

  const totals = {
    entradas: data.reduce((s, d) => s + d.entradas, 0),
    saidas: data.reduce((s, d) => s + d.saidas, 0),
  };
  const margin = { top: 12, right: 8, bottom: 30, left: 36 };
  const innerW = Math.max(width - margin.left - margin.right, 100);
  const innerH = height - margin.top - margin.bottom;
  const max = niceMax(Math.max(1, ...data.flatMap((d) => [d.entradas, d.saidas])));
  const y = (v) => innerH - (v / max) * innerH;
  const group = innerW / data.length;
  const barW = Math.max(3, Math.min(14, (group - 10) / 2));
  const ticks = [0, 1, 2, 3, 4].map((i) => (max / 4) * i);

  return (
    <div className="chart">
      <div className="chart-head">
        <div className="legend">
          <span><i style={{ background: SERIES.entradas }} /> Entradas · <b>{num(totals.entradas)} un.</b></span>
          <span><i style={{ background: SERIES.saidas }} /> Saídas · <b>{num(totals.saidas)} un.</b></span>
        </div>
        <button className="link-btn" onClick={() => setAsTable(!asTable)}>{asTable ? "Ver gráfico" : "Ver tabela"}</button>
      </div>

      {asTable ? (
        <div className="table-wrap">
          <table className="table compact">
            <thead><tr><th>Dia</th><th className="num">Entradas</th><th className="num">Saídas</th></tr></thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.date}><td>{weekday(d.date)} {dayMonth(d.date)}</td><td className="num">{d.entradas}</td><td className="num">{d.saidas}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={ref} className="chart-area" onMouseLeave={() => setHover(null)}>
          <svg width="100%" height={height} role="img" aria-label="Entradas e saídas por dia nos últimos 14 dias">
            <g transform={`translate(${margin.left},${margin.top})`}>
              {ticks.map((t) => (
                <g key={t} transform={`translate(0,${y(t)})`}>
                  <line x2={innerW} className={t === 0 ? "axis" : "grid"} />
                  <text x={-8} dy="0.32em" textAnchor="end" className="tick">{num(t)}</text>
                </g>
              ))}
              {data.map((d, i) => {
                const gx = i * group;
                const cx = gx + group / 2;
                return (
                  <g key={d.date}>
                    {hover === i && <rect x={gx + 2} y={0} width={group - 4} height={innerH} className="hover-band" rx={6} />}
                    <path d={columnPath(cx - barW - 1, y(d.entradas), barW, innerH - y(d.entradas))} fill={SERIES.entradas} />
                    <path d={columnPath(cx + 1, y(d.saidas), barW, innerH - y(d.saidas))} fill={SERIES.saidas} />
                    {(i % (width < 520 ? 3 : 2) === data.length % 2 || i === data.length - 1) && (
                      <text x={cx} y={innerH + 18} textAnchor="middle" className="tick">{dayMonth(d.date)}</text>
                    )}
                    <rect x={gx} y={0} width={group} height={innerH} fill="transparent"
                      onMouseEnter={() => setHover(i)} />
                  </g>
                );
              })}
            </g>
          </svg>
          {hover !== null && (
            <div className="tooltip" style={{
              left: Math.min(margin.left + hover * group + group / 2, width - 90),
              top: margin.top + 4,
            }}>
              <strong>{weekday(data[hover].date)}, {dayMonth(data[hover].date)}</strong>
              <div><i style={{ background: SERIES.entradas }} /> Entradas <b>{data[hover].entradas}</b></div>
              <div><i style={{ background: SERIES.saidas }} /> Saídas <b>{data[hover].saidas}</b></div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Valor em estoque por categoria (barras horizontais, uma cor só, ordenadas). */
export function CategoryBars({ data }) {
  const [hover, setHover] = useState(null);
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="hbars" onMouseLeave={() => setHover(null)}>
      {data.map((d) => (
        <div key={d.category} className={`hbar-row ${hover === d.category ? "hover" : ""}`}
          onMouseEnter={() => setHover(d.category)}>
          <span className="hbar-label">{d.category}</span>
          <div className="hbar-track">
            <div className="hbar-fill" style={{ width: `${(d.value / max) * 100}%` }} />
          </div>
          <span className="hbar-value">{brlCompact(d.value)}</span>
          {hover === d.category && (
            <div className="hbar-tip">{brl(d.value)} · {num(d.units)} un. · {d.items} item(ns)</div>
          )}
        </div>
      ))}
    </div>
  );
}

/** Saídas diárias de um item (14 dias), usado na previsão. */
export function HistoryBars({ values, height = 90 }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const max = Math.max(1, ...values);
  const gap = 2;
  const barW = Math.max(2, (width - gap * (values.length - 1)) / values.length);
  return (
    <div ref={ref} className="chart-area" onMouseLeave={() => setHover(null)}>
      <svg width="100%" height={height} role="img" aria-label="Saídas por dia nos últimos 14 dias">
        <line x1={0} x2={width} y1={height - 0.5} y2={height - 0.5} className="axis" />
        {values.map((v, i) => {
          const h = (v / max) * (height - 16);
          const x = i * (barW + gap);
          return (
            <g key={i} onMouseEnter={() => setHover(i)}>
              <path d={columnPath(x, height - h, barW, h)} fill={SERIES.entradas} opacity={hover === null || hover === i ? 1 : 0.45} />
              <rect x={x} y={0} width={barW + gap} height={height} fill="transparent" />
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div className="tooltip small" style={{ left: Math.min(hover * (barW + gap), width - 110), top: 0 }}>
          há {values.length - 1 - hover === 0 ? "0 dias (hoje)" : `${values.length - 1 - hover} dia(s)`}: <b>{values[hover]} un.</b>
        </div>
      )}
    </div>
  );
}
